from django.urls import path, include
from rest_framework.routers import DefaultRouter
from factchecker import views

router = DefaultRouter()
router.register(r'datasets', views.DatasetCatalogViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('query/', views.process_query, name='process-query'),
    path('waitlist/register/', views.register_waitlist, name='register_waitlist'),
    path('api/datasets/', views.get_datasets, name='get_datasets'),
    path('search/', views.search_datasets_api, name='search_datasets_api'),
    path('stream-search/', views.stream_search_datasets, name='stream_search_datasets'),
]