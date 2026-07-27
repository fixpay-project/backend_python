# Django Imports
from django.urls import path

# Project-Specific Imports
from .views import *

urlpatterns = [

    # CITY
    path('states/', RegionListView.as_view()),
    path('city/', CityList.as_view()),


]



