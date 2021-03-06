import json
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.core.urlresolvers import reverse
from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth.decorators import login_required

from django_openid_auth.views import parse_openid_response, login_complete
from django_openid_auth.auth import OpenIDBackend

from .models import AuthToken, User
from . import forms
from . import tasks
import games.models
import games.util.steam


def register(request):
    form = forms.RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return HttpResponseRedirect('/')
    return render(request, 'registration/registration_form.html',
                  {'form': form})


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(',')[0]
    else:
        ip_address = request.META.get('REMOTE_ADDR')
    return ip_address


@csrf_exempt
def client_auth(request):
    username = request.POST.get('username')
    password = request.POST.get('password')
    user = authenticate(username=username, password=password)
    if user and user.is_active:
        response_data = {'token': user.api_key.key}
    else:
        response_data = {'error': "Bad credentials"}
    return HttpResponse(json.dumps(response_data), mimetype="application/json")


@csrf_exempt
def client_verify(request):
    token = request.POST.get('token')
    try:
        auth_token = AuthToken.objects.get(token=token,
                                           ip_address=get_client_ip(request))
        response_data = {'username': auth_token.user.username}
    except AuthToken.DoesNotExist:
        response_data = {'error': 'invalid token'}
    return HttpResponse(json.dumps(response_data), mimetype="application/json")


@login_required
def profile(request):
    user = request.user
    return HttpResponseRedirect(reverse('user_account',
                                        args=(user.username, )))


def user_account(request, username):
    user = get_object_or_404(User, username=username)
    return render(request, "accounts/profile.jade", {'user': user})


@login_required
def profile_edit(request, username):
    user = get_object_or_404(User, username=username)
    if user != request.user:
        raise Http404
    form = forms.ProfileForm(request.POST or None, request.FILES or None,
                             instance=user)
    if form.is_valid():
        form.save()
        messages.success(
            request,
            'Your account info has been updated.'
        )
        return redirect(reverse('user_account', args=(username, )))
    return render(request, 'accounts/profile_edit.jade', {'form': form})


@csrf_exempt
def associate_steam(request):
    if not request.user.is_authenticated():
        return login_complete(request)
    else:
        openid_response = parse_openid_response(request)
        if openid_response.status == 'failure':
            messages.error(request, "Failed to associate Steam account")
            return redirect(
                reverse('user_account', args=(request.user.username, ))
            )
        openid_backend = OpenIDBackend()
        openid_backend.associate_openid(request.user, openid_response)
        request.user.set_steamid()
        request.user.save()
        return redirect(reverse("library_steam_sync"))


def library_show(request, username):
    user = User.objects.get(username=username)
    library = games.models.GameLibrary.objects.get(user=user)
    library_games = library.games.all()
    return render(request, 'accounts/library_show.jade',
                  {'user': user, 'games': library_games,
                   'is_library': True})


@login_required
def library_add(request, slug):
    user = request.user
    library = games.models.GameLibrary.objects.get(user=user)
    game = get_object_or_404(games.models.Game, slug=slug)
    library.games.add(game)
    return redirect(game.get_absolute_url())


@login_required
def library_remove(request, slug):
    user = request.user
    library = games.models.GameLibrary.objects.get(user=user)
    game = get_object_or_404(games.models.Game, slug=slug)
    library.games.remove(game)
    return redirect(request.META['HTTP_REFERER'])


@login_required
def library_steam_sync(request):
    user = request.user
    tasks.sync_steam_library.delay(user.id)
    messages.success(
        request,
        'Your Steam library is being synced with your Lutris account'
    )
    return redirect(reverse("library_show",
                            kwargs={'username': user.username}))
