"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from ninja_extra import NinjaExtraAPI
from ninja_jwt.controller import NinjaJWTDefaultController
from docs_app.api import DocumentController
from docs_app.auth_api import AuthController

api = NinjaExtraAPI()

api.register_controllers(NinjaJWTDefaultController)
api.register_controllers(DocumentController)
api.register_controllers(AuthController)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api.urls),
]
