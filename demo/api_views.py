from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.views import generic
from django.views.decorators.csrf import csrf_exempt

from .utils import radosBindings as rados
from .forms import CreateObjectForm, EditObjectForm, LoginForm

import json
from lxml import etree


# Django's default token generator
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
def authenticate_dtg(key, pk):
    try:
        user = User.objects.get(pk=pk)
    except:
        return False
    return default_token_generator.check_token(user, key) 

def authenticated_dtg(f):
    def wrapped(request, *args, **kwargs):
        token   = request.META.get('HTTP_X_AUTH_TOKEN', None)
        user_id = request.META.get('HTTP_USER', None)
        if token is None or user_id is None or \
            not authenticate_dtg(token, user_id):
            return response_code(401) # Unauthorized
        return f(request, *args, **kwargs)
    return wrapped


# rest framework's token authentication
from rest_framework.authtoken.models import Token
def get_user(key):
    try:
        return Token.objects.get(pk=key).user
    except:
        return None

def authenticated(f):
    def wrapped(request, *args, **kwargs):
        token = request.META.get('HTTP_X_AUTH_TOKEN', None)
        user = get_user(token)
        if user is None or user.username != kwargs['user_name']:
            return unothorized_error()
        request.user = user
        return f(request, *args, **kwargs)
    return wrapped

@csrf_exempt
def tokens(request):
    handlers = {
        'POST': send_token,
    }
    return dispatch(request, handlers)

def send_token(request):
    try:
        info = json.loads(request.body)
        user_info = info['auth']['identity']['password']['user']
        username = user_info['name']
        password = user_info['password']
    except ValueError:
        return malformed_json_error()

    user = authenticate(username=username, password=password)
    if user is None:
        return unothorized_error()
    token = Token.objects.get_or_create(user=user)[0]
    return response_token(token)


@csrf_exempt
@authenticated
def object_container(request, user_name):
    handlers = {
        'GET' : present_object_container(user_name),
        'POST': create_new_object(user_name),
    }
    return dispatch(request, handlers)

@csrf_exempt
@authenticated
def object_view(request, user_name, object_name):
    handlers = {
        'GET'   : present_object(user_name, object_name),
        'PUT'   : update_object(user_name, object_name),
        'DELETE': delete_object(user_name, object_name),
    }
    return dispatch(request, handlers)

def dispatch(request, handlers):
    if not request.method in handlers:
        return response_code(405)
    return handlers[request.method](request)


"""
    Object container API
"""
def present_object_container(user):
    def handler(request):
        content_type = request.META.get('CONTENT_TYPE', 'application/json')
        objects = sorted(rados.get_object_list(user))
        if 'application/xml' in content_type:
            return container_xml(request, objects)
        else:
            return container_json(request, objects)
    return handler

def container_xml(request, objects):
    root = etree.Element('container', name="objects")
    for o in objects:
        xml_object = etree.Element('object')
        name = etree.Element('name')
        name.text = str(o)
        xml_object.append(name)
        root.append(xml_object)
    document = etree.tostring(root, pretty_print=True)
    return HttpResponse(document, content_type="application/xml; charset=utf-8")

def container_json(request, objects):
    document = [{"name": o} for o in objects]
    return HttpResponse(serialize_json(document), 
                        content_type="application/json; charset=utf-8")

def create_new_object(user):
    def handler(request):
        object_name = request.POST.get('object_name', None)
        data        = request.POST.get('data', None)
        if object_name is None or data is None:
            return response_code(400) # invalid request
        if not rados.is_valid_name(object_name):
            return invalid_object_name_error()
        if not data:
            return empty_object_body_error()
        if rados.store_object(user, object_name, data):
            return object_created(user, object_name)
        else:
            return service_temporarily_unavailable_error()
    return handler

"""
    Object API
"""
def present_object(user, object_name):
    def handler(request):
        user = request.user.username
        data = rados.get_data(user, object_name)
        if data:
            return HttpResponse(data, content_type="text/plain")
        else:
            return response_code(404) # not found
    return handler

def update_object(user, object_name):
    def handler(request):
        if not rados.is_valid_name(object_name):
            return invalid_object_name_error()
        if not request.body:
            return empty_object_body_error()
        if rados.store_object(user, object_name, request.body):
            return object_created(user, object_name)
        else:
            return service_temporarily_unavailable_error()
    return handler

def delete_object(user, object_name):
    def handler(request):
        if rados.delete_object(user, object_name):
            return response_code(204) # no content
        else:
            return response_code(404) # not found
    return handler
        
"""
    Standard responses
"""
def object_created(user, object_name):
    document = \
    {
        "document":
        {
            "message": "Object created successfully.",
            "code"   : 201,
            "title"  : "Created",
            "uri"    : reverse('demo:api-object', args=(user, object_name,)),
        }
    }
    return HttpResponse(serialize_json(document), status=201,
                        content_type="application/json; charset=utf-8")

def invalid_object_name_error():
    document = \
    {
        "error":
        {
            "message": "Invalid object name. Please use only latin " + \
                        "characters, numbers and dashes.",
            "code"   : 400,
            "title"  : "Invalid object name.",
        }
    }
    return HttpResponse(serialize_json(document), status=400,
                        content_type="application/json; charset=utf-8")

def resource_not_found_error():
    document = \
    {
        "error": 
        {
            "message": "The resource could not be found.", 
            "code"   : 404, 
            "title"  : "Not Found",
        }
    }
    return HttpResponse(serialize_json(document), status=404,
                        content_type="application/json; charset=utf-8")

def service_temporarily_unavailable_error():
    document = \
    {
        "error": 
        {
            "message": "Sorry, your request could not be completed. " + \
                       "The service is temporarily unavailable.",
            "code"   : 503, 
            "title"  : "Service Temporarily Unavailable",
        }
    }
    return HttpResponse(serialize_json(document), status=503,
                        content_type="application/json; charset=utf-8")

def empty_object_body_error():
    document = \
    {
        "error": 
        {
            "message": "Sorry, to comply with the sub-standard error checking of " + \
                       "this procect the contents of an object cannot be empty. " + \
                       "Please provide a message body.",
            "code"   : 400,
            "title"  : "Empty Object",
        }
    }
    return HttpResponse(serialize_json(document), status=400,
                        content_type="application/json; charset=utf-8")

def malformed_json_error():
    document = \
    {
        "error": 
        {
            "message": "Expecting to find valid JSON in request body - the server " + \
                       "could not comply with the request since it is either " + \
                       "malformed or otherwise incorrect. The client is assumed " + \
                       "to be in error (as usual).", 
            "code"   : 400, 
            "title"  : "Bad Request",
        }
    }
    return HttpResponse(serialize_json(document), status=400,
                        content_type="application/json; charset=utf-8")

def unothorized_error():
    document = \
    {
        "error": 
        {
            "message": "Your request could not be authorized.",
            "code"   : 401, 
            "title"  : "Bad Request",
        }
    }
    return HttpResponse(serialize_json(document), status=401,
                        content_type="application/json; charset=utf-8")

def response_token(token):
    response = HttpResponse("", status=201, content_type="application/json; charset=utf-8")
    response['X-Subject-Token'] = token
    return response

def response_code(code):
    return HttpResponse(status=code, content_type="text/html; charset=UTF-8")

def serialize_json(json_object):
    return json.dumps(json_object, sort_keys=True, indent=4, separators=(',', ': ')) + '\n'

