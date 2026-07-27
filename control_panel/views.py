# Django Core Imports
from django.shortcuts import render
from django.core.paginator import Paginator, EmptyPage
from django.core.exceptions import ValidationError

# Django REST Framework Imports
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status

# Standard Library Imports
from io import StringIO
import csv

# Local Application Imports
from ssepl_backend.custom_jwt_auth import ( IsAdmin, IsSuperAdmin, IsRetailer, IsDistributor, CustomJWTAuthentication)
from .serializers import *

#---->START CODE :

# #STATE
class RegionListView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsAdmin | IsRetailer | IsSuperAdmin]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        if "file" in request.data:
            return self.create_state(request)
        return self.fetch_states(request)

    def create_state(self, request):
        try:
            csv_file = request.FILES.get("file")
            if not csv_file.name.endswith(".csv"):
                return Response({'status':'message',"message": "Please upload a CSV file."}, status=status.HTTP_400_BAD_REQUEST)

            csv_data = StringIO(csv_file.read().decode())
            reader = csv.DictReader(csv_data)

            for row in reader:
                serializer = StateSerializer(data=row)
                if serializer.is_valid():
                    serializer.save()
                else:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            return Response({"status": "success", "message": "CSV data processed successfully."}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def fetch_states(self, request):
        try:
            state_name = request.data.get("state_name")
            page_size = int(request.data.get("page_size", 10))
            page_number = int(request.data.get("page_number", 1))

            states = State.objects.all()
            if state_name:
                states = states.filter(state_name__icontains=state_name)

            paginator = Paginator(states, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({"status": "fail", "message": "Page not found.", "data": {}}, status=status.HTTP_404_NOT_FOUND)

            state_serializer = StateSerializer(page_obj.object_list, many=True, context={"exclude_fields": ["created_at", "is_active", "create_by", "update_at", "update_by"]})
            paginated_response_data = {
                "total_pages": paginator.num_pages,
                "current_page": page_obj.number,
                "total_items": paginator.count,
                "results": state_serializer.data,
            }
            return Response({"status": "success", "message": "State Data", "data": paginated_response_data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


#CITY
class CityList(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsDistributor | IsAdmin | IsRetailer | IsSuperAdmin]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        if "file" in request.data:
            return self.create_city(request)
        return self.fetch_cities(request)

    def create_city(self, request):
        try:
            csv_file = request.FILES.get("file")
            if not csv_file.name.endswith(".csv"):
                return Response({'status':'error',"message": "Please upload a CSV file."}, status=status.HTTP_400_BAD_REQUEST)

            csv_data = StringIO(csv_file.read().decode())
            reader = csv.DictReader(csv_data)

            for row in reader:
                serializer = CitySerializer(data=row)
                if serializer.is_valid():
                    serializer.save()
                else:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            return Response({"status": "success", "message": "CSV data processed successfully."}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def fetch_cities(self, request):
        try:
            state_id = request.data.get("state_id")
            city_name = request.data.get("search")
            page_size = int(request.data.get("page_size", 10))
            page_number = int(request.data.get("page_number", 1))

            cities = City.objects.all()
            if state_id:
                cities = cities.filter(state_id=state_id)
            if city_name:
                cities = cities.filter(city_name__icontains=city_name)

            paginator = Paginator(cities, page_size)
            try:
                page_obj = paginator.page(page_number)
            except EmptyPage:
                return Response({"status": "fail", "message": "Page not found.", "data": {}}, status=status.HTTP_404_NOT_FOUND)

            city_serializer = CitySerializer(page_obj.object_list, many=True, context={"exclude_fields": ["created_at", "is_active", "create_by", "update_at", "update_by", "state_id"]})
            paginated_response_data = {
                "total_pages": paginator.num_pages,
                "current_page": page_obj.number,
                "total_items": paginator.count,
                "results": city_serializer.data,
            }
            return Response({"status": "success", "message": "City Data", "data": paginated_response_data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
