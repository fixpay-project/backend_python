from django.urls import path
from .views import *

urlpatterns = [

    # Admin web portal site url

    path('banner/', BannerAPIView.as_view()),

    path('partner/', PartnerAPIView.as_view()),

    path('news/latter/', NewsLatterAPIView.as_view()),

    path('aboutus/', AboutUsAPIView.as_view()),

    path('service/group/', ServiceGroupAPIView.as_view()),

    path('service/', ServiceAPIView.as_view()),

    path('random/stuff/', RandomStuffAPIView.as_view()),

    path('contact/enquiry/', ContactEnquiryAPIView.as_view()),

    # static site url

    path('web/contact/', ContactUsAPIView.as_view()),

    path('news/latter/add/', NewsAPIView.as_view()),

    path('web/banner/', BannerGetAPIView.as_view()),

    path('web/partner/', PartnerGetAPIView.as_view()),

    path('web/aboutus/', AboutUsGetAPIView.as_view()),

    path('web/service/group/', ServiceGroupGetAPIView.as_view()),

    path('web/service/', ServiceGetAPIView.as_view()),

    path('web/random/stuff/', RandomStuffGetAPIView.as_view()),

]
