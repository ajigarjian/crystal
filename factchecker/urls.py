from django.urls import path, include
from rest_framework.routers import DefaultRouter
from factchecker import views

router = DefaultRouter()
router.register(r'datasets', views.DatasetCatalogViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('query/', views.process_query, name='process-query'),
]