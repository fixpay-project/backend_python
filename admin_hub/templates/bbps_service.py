from .views import *
import hashlib
import binascii
from xml.dom.minidom import parseString
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import random
import string
from rest_framework.decorators import api_view
from xml.etree.ElementTree import Element, SubElement, tostring
import xmltodict
from datetime import datetime
import xml.etree.ElementTree as ET
from .commission_calculations import *
from .utilies import *
from rest_framework.exceptions import ValidationError
from django.conf import settings

BBPS_AGENT_ID = getattr(settings, 'BBPS_AGENT_ID', 'CC01MS76AGTU00000001')
BBPS_INIT_CHANNEL = getattr(settings, 'BBPS_INIT_CHANNEL', 'AGT')




def unpad(data, block_size):
    pad_len = data[-1]
    if pad_len > block_size:
        raise ValueError("Invalid padding")
    return data[:-pad_len]


def hextobin(hex_string):
    return binascii.unhexlify(hex_string)


def pad(data, block_size):
    pad_len = block_size - len(data) % block_size
    return data + bytes([pad_len] * pad_len)


def generate_random_filename(extension="xml"):
    """Generate a random filename with the specified extension."""
    random_name = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    return f"{random_name}.{extension}"


class EncryptData(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        try:
            key = "13D6751278DC844724FB7A5AC512276E"
            key = hextobin(hashlib.md5(key.encode()).hexdigest())
            init_vector = bytes(
                [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f])

            plain_text = request.data.get('plain_text')
            # if not uploaded_file:
            #     return Response({"error": "File not provided."}, status=status.HTTP_400_BAD_REQUEST)

            # plain_text = uploaded_file.read().decode()

            cipher = AES.new(key, AES.MODE_CBC, init_vector)
            plain_text_padded = pad(plain_text.encode(), AES.block_size)
            encrypted_text = cipher.encrypt(plain_text_padded)
            encrypted_hex = binascii.hexlify(encrypted_text).decode()

            storage_path = getattr(settings, 'ENCRYPTED_FILES_DIR', './encrypted_files/')
            os.makedirs(storage_path, exist_ok=True)

            file_name = generate_random_filename("enc")
            file_path = os.path.join(storage_path, file_name)
            with open(file_path, 'w') as file:
                file.write(encrypted_hex)

            return Response({"message": "File encrypted and saved successfully.", "file_name": file_name},
                            status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ConvertXmlToJson(APIView):
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        xml_file = request.FILES.get('xml_data')
        print('xml data', xml_file)
        try:
            # Parse the XML file
            xml_content = xml_file.read()  # Read the file's content
            dict_data = xmltodict.parse(xml_content)  # Convert XML to dictionary

            # Convert dictionary to JSON
            json_data = json.dumps(dict_data, indent=4)

            # Define file path for saving JSON
            storage_path = getattr(settings, 'JSON_FILES_DIR', './json_files/')
            os.makedirs(storage_path, exist_ok=True)

            file_name = generate_random_filename("json")
            file_path = os.path.join(storage_path, file_name)

            # Save the JSON data to a file
            with open(file_path, "w", encoding="utf-8") as json_file:
                json_file.write(json_data)
            json_data_data = json.loads(json_data)
            return Response({
                "message": "XML data converted to JSON successfully.",
                "json_data": json_data_data,
                # "file_path": file_path
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": f"An error occurred: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BbpsBillerAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsRetailer]

    def post(self, request):
        if 'is_categorey' in request.data and 'page_number' in request.data and 'page_size' in request.data:
            return self.get_bbps_biller_category(request)
        elif 'category_id' in request.data and 'page_number' in request.data and 'page_size' in request.data:
            return self.get_bbps_biller_list(request)
        elif 'blr_id' in request.data and 'page_number' in request.data and 'page_size' in request.data:
            return self.get_bbps_biller_details(request)
        elif 'blr_id' in request.data and 'blr_request_id' in request.data and 'blr_payment_request_data' in request.data:
            return self.bill_payment(request)
        elif 'blr_id' in request.data and 'blr_request_data':
            return self.fetch_biller_request(request)
        elif 'request_id' in request.data and 'page_number' in request.data and 'page_size' in request.data:
            return self.update_bbps_biller_status(request)
        elif 'page_number' in request.data or 'page_size' in request.data and 'transaction_data' in request.data:
            return self.get_bbps_biller_transaction_list(request)
        else:
            return Response({'status': 'fail', 'message': 'Invalid request data.'}, status=status.HTTP_400_BAD_REQUEST)

    def encrypt_data(self, xml_data):
        try:
            key = "13D6751278DC844724FB7A5AC512276E"
            key = hextobin(hashlib.md5(key.encode()).hexdigest())
            init_vector = bytes(
                [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f])

            cipher = AES.new(key, AES.MODE_CBC, init_vector)
            plain_text_padded = pad(xml_data.encode(), AES.block_size)
            encrypted_text = cipher.encrypt(plain_text_padded)
            encrypted_hex = binascii.hexlify(encrypted_text).decode()

            return encrypted_hex

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def decrypt_data(self, string_data):
        try:
            encrypted_text = string_data
            # Define the decryption key and initialization vector
            key = "13D6751278DC844724FB7A5AC512276E"
            key = hextobin(hashlib.md5(key.encode()).hexdigest())
            init_vector = bytes(
                [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f])

            # Decrypt the data
            encrypted_text_bytes = binascii.unhexlify(encrypted_text)
            cipher = AES.new(key, AES.MODE_CBC, init_vector)
            decrypted_text_padded = cipher.decrypt(encrypted_text_bytes)
            decrypted_text = unpad(decrypted_text_padded, AES.block_size).decode()
            decrypted_xml = ET.fromstring(decrypted_text)

            storage_path = getattr(settings, 'DECRYPTED_FILES_DIR', './decrypted_files/')
            os.makedirs(storage_path, exist_ok=True)

            file_name = generate_random_filename("dec")
            file_path = os.path.join(storage_path, file_name)
            with open(file_path, 'wb') as file:
                file.write(ET.tostring(decrypted_xml, encoding='utf-8', xml_declaration=True))

            xml = ET.tostring(decrypted_xml, encoding='utf-8', xml_declaration=True)

            return xml

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def xml_to_json(self, xml_data):
        try:

            # Convert XML to dictionary
            dict_data = xmltodict.parse(xml_data)

            # Convert dictionary to JSON
            json_data = json.dumps(dict_data, indent=4)

            # Return success response
            return json_data

        except Exception as e:
            # Handle any exceptions and return error response
            return Response({
                "error": f"An error occurred: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def generate_reference_id(self):
        random_chars = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=27))

        now = datetime.datetime.now()

        year_last_digit = str(now.year)[-1]
        day_of_year = f"{now.timetuple().tm_yday:03d}"
        hour = f"{now.hour:02d}"
        minute = f"{now.minute:02d}"

        julian_suffix = f"{year_last_digit}{day_of_year}{hour}{minute}"

        reference_id = random_chars + julian_suffix
        return reference_id

    def get_bbps_biller_category(self, request):
        page_number = request.data.get('page_number', 1)
        page_size = request.data.get('page_size', 10)
        search = request.data.get('search', '')
        try:
            all_categories = BBPSBillerCategory.objects.filter(is_deleted=False, is_deactive=False)
            if search != '':
                all_categories = all_categories.filter(category_name__icontains=search)
            serializer = BBPSBillerCategorySerializer(all_categories, many=True)
            data = {
                'results': serializer.data
            }
            return Response({'status': 'success', 'message': 'get all bbps category', 'data': data},
                            status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_400_BAD_REQUEST)

    def get_bbps_biller_list(self, request):
        category_id = request.data.get('category_id')

        try:
            # Use filter() to retrieve multiple records
            fetch_info = BBPSBiller.objects.filter(bbps_category__bbps_id=category_id, is_deleted=False,
                                                   is_deactive=False)

            if not fetch_info.exists():
                return Response({'status': 'fail', 'message': 'Biller not found.'}, status=status.HTTP_404_NOT_FOUND)

            # Serialize the queryset
            serializer = BBPSBillerSerializer(fetch_info, many=True)
            data = {
                'results': serializer.data
            }
            return Response({'status': 'success', 'data': data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'status': 'fail', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_400_BAD_REQUEST)

    def get_bbps_biller_details(self, request):
        blr_id = request.data.get('blr_id')
        

        try:
            bbps_biller_details = BBPSBillResponse.objects.get(bbps_biller_id=blr_id)
            serializer = BBPSBillerResponseSerializer(bbps_biller_details)
            json_data = json.loads(serializer.data.get('bbps_biller_response'))
            if type(json_data.get('billerInputParams').get("paramInfo")) == list:
                list_data = json_data.get('billerInputParams').get("paramInfo")
            else:
                list_data = [json_data.get('billerInputParams').get("paramInfo")]
            
            split_mode = json_data.get('billerPaymentModes').replace(' ', '').split(',')
            if 'UPI' in split_mode:
                channel_info = json_data.get('billerPaymentChannels').get('paymentChannelInfo')
                for info in channel_info:
                    if info.get('paymentChannelName') == 'INT':
                        minimum = info.get('minAmount')
                        maximum = info.get('maxAmount')
                    

                        
                data = {'results': {'billerInfoResponse': list_data,
                                    'billerId': json_data.get('billerId'), 'billerAdhoc': json_data.get('billerAdhoc'),
                                    'min': minimum, 'max': maximum, 'cash': True}}
                
            else:
                data = {'results': {'billerInfoResponse': list_data,
                                    'billerId': json_data.get('billerId'), 'billerAdhoc': json_data.get('billerAdhoc'),
                                    'cash': False}}
            return Response({'status': 'success', 'message': 'Get bbps biller details', 'data': data},
                            status=status.HTTP_200_OK)
        except BBPSBiller.DoesNotExist:
            return Response({'status': 'fail', 'message': 'Biller not found.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'status': 'fail', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_400_BAD_REQUEST)

    def fetch_biller_request(self, request):
        user = request.user 
        blr_id = request.data.get('blr_id')
        contact_number = request.data.get('contact_no')
        blr_request_data = request.data.get('blr_request_data')
       
        
        

        try:
            convert_blr_request_data = json.loads(blr_request_data)

            # Root element
            root = ET.Element("billFetchRequest")

            # Static data
            agent_id = ET.SubElement(root, "agentId")
            agent_id.text = BBPS_AGENT_ID

            agent_device_info = ET.SubElement(root, "agentDeviceInfo")
            ip = ET.SubElement(agent_device_info, "ip")
            ip.text = "110.227.212.120"

            init_channel = ET.SubElement(agent_device_info, "initChannel")
            init_channel.text = BBPS_INIT_CHANNEL

            mac = ET.SubElement(agent_device_info, "mac")
            mac.text = "94-BB-43-F0-FB-C8"

            customer_info = ET.SubElement(root, "customerInfo")
            customer_mobile = ET.SubElement(customer_info, "customerMobile")
            customer_mobile.text = contact_number

            customer_email = ET.SubElement(customer_info, "customerEmail")
            customer_email.text = ""

            customer_adhaar = ET.SubElement(customer_info, "customerAdhaar")
            customer_adhaar.text = ""

            customer_pan = ET.SubElement(customer_info, "customerPan")
            customer_pan.text = ""

            biller_id = ET.SubElement(root, "billerId")
            biller_id.text = blr_id

            # Dynamic input parameters
            input_params = ET.SubElement(root, "inputParams")
            for param in convert_blr_request_data:
                input_element = ET.SubElement(input_params, "input")

                param_name = ET.SubElement(input_element, "paramName")
                param_name.text = param.get("paramName", "")

                param_value = ET.SubElement(input_element, "paramValue")
                param_value.text = param.get("paramValue", "")

            # Convert to string
            xml_data = ET.tostring(root, encoding="unicode")
            encrypted_data = self.encrypt_data(xml_data)
            request_id = self.generate_reference_id()

            url = "https://api.billavenue.com/billpay/extBillCntrl/billFetchRequest/xml"
            parems = {
                'accessCode': 'AVVK43CB13NO66SBFK',
                'requestId': request_id,
                'ver': '1.0',
                'instituteId': 'MS76',
                'encRequest': encrypted_data
            }

            response = requests.post(url, params=parems)
            print('===>', response.text)
            decrypt_data = self.decrypt_data(response.text)
            print('===>', decrypt_data)
            xml_to_json = self.xml_to_json(decrypt_data)
            json_data = json.loads(xml_to_json)


            json_data = json.loads(xml_to_json)

                
            

            # Append log to a text file
            with open("bill_fetch_log.txt", "a", encoding="utf-8") as log_file:
                log_file.write(json.dumps(json_data, indent=4) + "\n\n")
                log_file.write(json.dumps(response.text, indent=4) + "\n\n")

            if response.status_code == 200:
                if json_data.get('billFetchResponse').get('responseCode') == "000":
                    bill_payment = BBPSBillPayment.objects.create(
                        bbps_request_id=request_id,
                        bbps_bill_fetch_response=json_data,
                        bbps_contact_no=contact_number,
                        bbps_blr_id=blr_id,
                        created_by=request.user.id
                    )
                    data = {'results': {'bill_request_id': request_id, 'bill_request_resposne': json_data}}
                    user_activity = {
                        "table_id": bill_payment.pk,
                        "table_name": 'ad_bbps_bill_payment',
                        "ua_action": 'Create',  # Action performed
                        "ua_description": 'Bill Fetch Request successfully.',  # Action description
                        "created_by": request.user,  # Current user performing the action
                        "request_data": dict(request.data),  # Request data
                        "response_data": model_to_dict(bill_payment)
                    }

                    add_user_activity(user_activity)
                    return Response({'status': 'success', 'message': 'Get Biller Fetch Request', 'data': data},
                                    status=status.HTTP_200_OK)
                else:
                    message = json_data.get('billFetchResponse').get('errorInfo').get('error').get('errorMessage')
                    return Response({'status': 'fail', 'message': message}, status=status.HTTP_200_OK)

            else:
                return Response({'status': 'fail', 'message': response.text, 'data': json_data},
                                status=status.HTTP_400_BAD_REQUEST)

        except json.JSONDecodeError:
            return Response({"status": "fail", "message": "blr_request_data must be valid JSON."},
                            status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            with open("bill_fetch_log.txt", "a", encoding="utf-8") as log_file:
                log_file.write(str(e), indent=4)
            return Response({'status': 'fail', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_400_BAD_REQUEST)

    def bill_payment(self, request):
        blr_id = request.data.get('blr_id')
        contact_no = request.data.get('contact_no')
        amount = request.data.get('amount')
        formatted_amount = "{:.2f}".format(float(amount) / 100)
        blr_request_id = request.data.get('blr_request_id')
        sp_id = request.data.get('sp_id')
        blr_payment_request_data = request.data.get('blr_payment_request_data')
        
        try:
            # admin_wallet = check_admin_wallet(request, formatted_amount)

            # retailer_wallet = check_retailer_wallet(request, formatted_amount, request.user.id)

            # if not float(PortalUserWallet.objects.get(pu_id=1).main_wallet) > 0.00 and not float(PortalUserWallet.objects.get(pu_id=1).main_wallet) > float(amount):
            #     return Response({'status': 'fail', 'message': 'Admin wallet has insufficient balance'}, status=status.HTTP_200_OK)
            if not float(PortalUserWallet.objects.get(pu_id=request.user.id).main_wallet) > 0.00 and not float(
                    PortalUserWallet.objects.get(pu_id=request.user.id).main_wallet) > float(amount):
                return Response({'status': 'fail', 'message': 'User wallet has insufficient balance'},
                                status=status.HTTP_200_OK)

            biller = BBPSBillPayment.objects.get(bbps_request_id=blr_request_id, bbps_contact_no=contact_no)
            sp = AdServiceProvider.objects.get(sp_id=sp_id)
            additional_info_data = None
            biller_response_data = biller.bbps_bill_fetch_response.get('billFetchResponse').get('billerResponse')
            if biller.bbps_bill_fetch_response.get('billFetchResponse').get('additionalInfo'):
                
                additional_info_data = biller.bbps_bill_fetch_response.get('billFetchResponse').get(
                    'additionalInfo').get('info')
                if isinstance(additional_info_data, dict):
                    additional_info_data = [additional_info_data]


            convert_blr_payment_request_data = json.loads(blr_payment_request_data)

            # Root element
            root = ET.Element("billPaymentRequest")

            # Static data
            agent_id = ET.SubElement(root, "agentId")
            agent_id.text = BBPS_AGENT_ID

            biller_adhoc = ET.SubElement(root, "billerAdhoc")
            biller_adhoc.text = "false"

            agent_device_info = ET.SubElement(root, "agentDeviceInfo")
            ip = ET.SubElement(agent_device_info, "ip")
            ip.text = "110.227.212.120"

            init_channel = ET.SubElement(agent_device_info, "initChannel")
            init_channel.text = BBPS_INIT_CHANNEL

            mac = ET.SubElement(agent_device_info, "mac")
            mac.text = "94-BB-43-F0-FB-C8"

            # Customer Info (static for now)
            customer_info = ET.SubElement(root, "customerInfo")
            customer_mobile = ET.SubElement(customer_info, "customerMobile")
            customer_mobile.text = contact_no
            customer_email = ET.SubElement(customer_info, "customerEmail")
            customer_email.text = ""
            customer_adhaar = ET.SubElement(customer_info, "customerAdhaar")
            customer_adhaar.text = ""
            customer_pan = ET.SubElement(customer_info, "customerPan")
            customer_pan.text = ""

            biller_id = ET.SubElement(root, "billerId")
            biller_id.text = blr_id

            # Dynamic input parameters
            input_params = ET.SubElement(root, "inputParams")
            for param in convert_blr_payment_request_data:
                input_element = ET.SubElement(input_params, "input")

                param_name = ET.SubElement(input_element, "paramName")
                param_name.text = param.get("paramName", "")

                param_value = ET.SubElement(input_element, "paramValue")
                param_value.text = param.get("paramValue", "")

            # Dynamic biller response
            biller_response = ET.SubElement(root, "billerResponse")
            for key, value in biller_response_data.items():
                response_element = ET.SubElement(biller_response, key)
                response_element.text = str(value)

            

            
            
            # if additional_info_data:
            #     additional_info = ET.SubElement(root, "additionalInfo")

            #     # Ensure `additional_info_data` is always a list for uniform processing
            #     if isinstance(additional_info_data, dict):
            #         additional_info_data = [additional_info_data]

            #     for info in additional_info_data:
            #         info_element = ET.SubElement(additional_info, "info")

            #         info_name = ET.SubElement(info_element, "infoName")
            #         info_name.text = info.get("infoName", "")

            #         info_value = ET.SubElement(info_element, "infoValue")
            #         info_value.text = str(info.get("infoValue", ""))

            

            # if additional_info_data:
            #     additional_info = ET.SubElement(root, "additionalInfo")
            #     for info in additional_info_data:
            #         info_element = ET.SubElement(additional_info, "info")
            #         info_name = ET.SubElement(info_element, "infoName")
            #         info_name.text = info.get("infoName", "")
            #         info_value = ET.SubElement(info_element, "infoValue")
            #         info_value.text = str(info.get("infoValue", ""))

            if additional_info_data:
                additional_info = ET.SubElement(root, "additionalInfo")


                if isinstance(additional_info_data, dict):
                    additional_info_data = [additional_info_data]

                for info in additional_info_data:
                    info_element = ET.SubElement(additional_info, "info")

                    info_name = ET.SubElement(info_element, "infoName")
                    info_name.text = info.get("infoName", "")

                    info_value = ET.SubElement(info_element, "infoValue")
                    info_value.text = str(info.get("infoValue", ""))

                
            
                    
        

            # Amount Info (static for now)
            amount_info = ET.SubElement(root, "amountInfo")

            
            # Use a different variable name for the XML element
            amount_element = ET.SubElement(amount_info, "amount")
            amount_element.text = amount  # Set the value fetched from request.data

            

            currency = ET.SubElement(amount_info, "currency")
            currency.text = "356"

            

            cust_conv_fee = ET.SubElement(amount_info, "custConvFee")
            cust_conv_fee.text = "0"

            

            amount_tags = ET.SubElement(amount_info, "amountTags")
            amount_tags.text = ""


            

            # Payment Method (static for now)
            payment_method = ET.SubElement(root, "paymentMethod")
            payment_mode = ET.SubElement(payment_method, "paymentMode")
            payment_mode.text = "UPI"
            quick_pay = ET.SubElement(payment_method, "quickPay")
            quick_pay.text = "N"
            split_pay = ET.SubElement(payment_method, "splitPay")
            split_pay.text = "N"

            
            # Payment Info (static for now)
            payment_info = ET.SubElement(root, "paymentInfo")
            payment_info_entry = ET.SubElement(payment_info, "info")
            info_name = ET.SubElement(payment_info_entry, "infoName")
            info_name.text = "VPA"
            info_value = ET.SubElement(payment_info_entry, "infoValue")
            info_value.text = "gaurangkumar@upi"

            
            # Convert to string
            xml_data = ET.tostring(root, encoding="unicode")
            encrypt_data = self.encrypt_data(xml_data)


            with open("bill_payment_log.txt", "a") as log_file:
                log_file.write(f"Request XML:\n{xml_data}\n")
            url = "https://api.billavenue.com/billpay/extBillPayCntrl/billPayRequest/xml"
            parems = {
                 'accessCode': 'AVVK43CB13NO66SBFK',
                 'requestId': blr_request_id,
                 'ver': '1.0',
                 'instituteId': 'MS76',
                 'encRequest': encrypt_data
            }
            
            response = requests.post(url, params=parems)
            
            
            decrypt_data = self.decrypt_data(response.text)

            xml_to_json = self.xml_to_json(decrypt_data)
            xml = json.loads(xml_to_json)

            with open("bill_payment_log.txt", "a") as log_file:
                log_file.write(f"Response JSON:\n{json.dumps(xml, indent=4)}\n")

            if response.status_code == 200:
                if xml.get('ExtBillPayResponse').get('responseCode') == "000":
                    formatted_amount = "{:.2f}".format(float(amount) / 100)

                    biller.bbps_payment_response = xml
                    biller.updated_at = datetime.datetime.now()
                    biller.bbps_amount = formatted_amount
                    biller.bbps_sp = sp
                    biller.bbps_status = 'SUCCESS'
                    biller.save()

                    category = BBPSBiller.objects.filter(bbps_blr_id=blr_id).first()

                    service_provider = AdServiceProvider.objects.get(sp_id=sp_id)

                    gst_rate = service_provider.hsn_sac.tax_rate

                    admin_rate = float(category.bbps_category.to_us_charges.get('rate_value'))
                    admin_rate_type = category.bbps_category.to_us_charges.get('rate_type')
                    admin_charges_type = category.bbps_category.to_us_charges.get('charge_type')

                    char_comm_amt = float(formatted_amount) * (
                                admin_rate / 100) if admin_rate_type == 'is_percent' else admin_rate
                    admin_tax_amt = float(char_comm_amt) - (float(char_comm_amt) / (1 + (float(gst_rate) / 100)))

                    portal_user_details = PortalUserDetails.objects.get(pu_id=request.user.id)

                    # for retailer
                    rt_gl = GlTrn.objects.create(
                        service_trn_id=biller.pk,
                        pu_id=request.user.id,
                        gl_trn_amt=formatted_amount,
                        effectvie_wallet='main_wallet',
                        effectvie_amt=formatted_amount,
                        service_trn_table='ad_bbps_service_trnasaction',
                        effective_type='DR',
                        gl_trn_dt=now(),
                    )

                    WalletTrn.objects.create(
                        action_id=rt_gl.pk,
                        action_type='Order',
                        pu_id=request.user.id,
                        wl_label=f"BBPS_by_{portal_user_details.pud_unique_id}_of_amount_{formatted_amount}_with_tx_id_{biller.bbps_request_id}",
                        effectvie_wallet='main_wallet',
                        effectvie_amt=formatted_amount,
                        effective_type='DR',
                        wl_trn_dt=now()
                    )

                    rtl_wallet = PortalUserWallet.objects.get(pu_id=request.user.id)
                    rtl_wallet.main_wallet = float(rtl_wallet.main_wallet) - float(formatted_amount)
                    rtl_wallet.updated_at = now()
                    rtl_wallet.save()

                    # for admin

                    admin_gl = GlTrn.objects.create(
                        service_trn_id=biller.pk,
                        pu_id=1,
                        gl_trn_amt=formatted_amount,
                        effectvie_wallet='main_wallet',
                        effectvie_amt=formatted_amount,
                        service_trn_table='ad_bbps_service_trnasaction',
                        effective_type='DR',
                        gl_trn_dt=now(),
                    )

                    WalletTrn.objects.create(
                        action_id=admin_gl.pk,
                        action_type='Order',
                        pu_id=1,
                        wl_label=f"BBPS_by_{portal_user_details.pud_unique_id}_of_amount_{formatted_amount}_with_tx_id_{biller.bbps_request_id}",
                        effectvie_wallet='main_wallet',
                        effectvie_amt=formatted_amount,
                        effective_type='DR',
                        wl_trn_dt=now()
                    )

                    admin_wallet = PortalUserWallet.objects.get(pu_id=1)
                    admin_wallet.main_wallet = float(admin_wallet.main_wallet) - float(formatted_amount)
                    admin_wallet.updated_at = now()
                    admin_wallet.save()

                    admin_gl = GlTrn.objects.create(
                        service_trn_id=biller.pk,
                        pu_id=1,
                        gl_tax_rate=gst_rate,
                        gl_tax_amt=admin_tax_amt,
                        gl_trn_amt=formatted_amount,
                        effectvie_wallet='main_wallet',
                        effectvie_amt=char_comm_amt,
                        service_trn_table='ad_bbps_service_trnasaction',
                        effective_type=admin_charges_type,
                        gl_trn_dt=now(),
                    )

                    WalletTrn.objects.create(
                        action_id=biller.pk,
                        action_type='Order',
                        pu_id=1,
                        wl_label=f"BBPS_by_{portal_user_details.pud_unique_id}_of_amount_{formatted_amount}_with_tx_id_{biller.bbps_request_id}",
                        effectvie_wallet='main_wallet',
                        effectvie_amt=char_comm_amt,
                        effective_type=admin_charges_type,
                        wl_trn_dt=now()
                    )

                    admin_wallet = PortalUserWallet.objects.get(pu_id=1)
                    if admin_charges_type == 'CR':
                        admin_wallet.main_wallet = float(admin_wallet.main_wallet) + float(char_comm_amt)
                    else:
                        admin_wallet.main_wallet = float(admin_wallet.main_wallet) - float(char_comm_amt)
                    admin_wallet.updated_at = now()
                    admin_wallet.save()
                    data = {
                        'order_amount': formatted_amount,
                        'id': request.user.id,
                        'sp_id': sp_id,
                        'customer_contact_no': contact_no,
                        'customer_name': None,
                        'trn_response': xml,
                        'service_trn': biller.pk,
                        'label': service_provider.label,
                        'category': category.bbps_category.bbps_id,
                        'table_name': 'ad_bbps_service_transaction'
                    }

                    after_tx_cal(request, data)

                    user_activity = {
                        "table_id": biller.pk,
                        "table_name": 'ad_bbps_bill_payment',
                        "ua_action": 'Create',  # Action performed
                        "ua_description": 'Bill Payment successfully.',  # Action description
                        "created_by": request.user,  # Current user performing the action
                        "request_data": dict(request.data),  # Request data
                        "response_data": model_to_dict(biller)
                    }

                    add_user_activity(user_activity)
                    return Response({'status': 'success', 'message': 'Bill Payment Successfully.'},
                                    status=status.HTTP_200_OK)

                elif xml.get('ExtBillPayResponse').get('responseCode') == "204":
                    message = xml.get('ExtBillPayResponse').get('errorInfo').get('error').get('errorMessage')
                    return Response({'status': 'fail', 'message': message}, status=status.HTTP_200_OK)
                else:
                    message = xml.get('ExtBillPayResponse').get('errorInfo').get('error').get('errorMessage')
                    return Response({'status': 'fail', 'message': message}, status=status.HTTP_200_OK)

            else:
                biller.bbps_status = 'FAILED'
                biller.updated_at = datetime.datetime.now()
                biller.save()
                return Response({'status': 'fail', 'message': response.text, 'data': xml_to_json},
                                status=status.HTTP_400_BAD_REQUEST)

        except json.JSONDecodeError:
            return Response({"status": "fail", "message": "blr_payment_request_data must be valid JSON."},
                            status=status.HTTP_400_BAD_REQUEST)

        except BBPSBillPayment.DoesNotExist:
            return Response({'status': 'fail', 'message': 'request id dose not exists.'},
                            status=status.HTTP_400_BAD_REQUEST)

        except AdServiceProvider.DoesNotExist:
            return Response({'status': 'fail', 'message': 'service provider not found.'},
                            status=status.HTTP_400_BAD_REQUEST)

        except ValidationError as e:
            message = str(e)
            if "ErrorDetail" in message:
                message = message.split("string='")[1].split("', code=")[0]
            return Response({'status': 'fail', 'message': message}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_400_BAD_REQUEST)

    def update_bbps_biller_status(self, request):
        trnasaction_request_id = request.data.get('request_id')
        print('trnasaction_request_id', trnasaction_request_id)
        try:
            update_status = BBPSBillPayment.objects.get(bbps_request_id=trnasaction_request_id)
            retailer = PortalUser.objects.get(id=request.user.id)

            # Generate XML
            root = ET.Element("transactionStatusReq")

            # Static data with proper formatting
            track_type = ET.SubElement(root, "trackType")
            track_type.text = "REQUEST_ID"

            track_value = ET.SubElement(root, "trackValue")
            track_value.text = trnasaction_request_id

            # Convert to XML string with declaration
            xml_data = ET.tostring(root, encoding="unicode")
            xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_data
            encrypt_data = self.encrypt_data(xml_declaration)
            request_id = self.generate_reference_id()

            url = "https://api.billavenue.com/billpay/transactionStatus/fetchInfo/xml"
            params = {
                'accessCode': 'AVVK43CB13NO66SBFK',
                'requestId': request_id,
                'ver': '1.0',
                'instituteId': 'MS76',
                'encRequest': encrypt_data
            }

            response = requests.post(url, params=params)
            decrypt_data = self.decrypt_data(response.text)

            xml_to_json = self.xml_to_json(decrypt_data)
            xml = json.loads(xml_to_json)

            if response.status_code == 200:
                if xml.get('transactionStatusResp', {}).get('responseCode') == "000":
                    biller_name = BBPSBiller.objects.get(
                        bbps_blr_id=xml.get('transactionStatusResp', {}).get('txnList', {}).get('billerId')
                    ).bbps_blr_name
                    bbps_response = BBPSBillPayment.objects.get(bbps_request_id=trnasaction_request_id)

                    # Fix: Properly parse the transaction date
                    txn_date_str = xml.get('transactionStatusResp', {}).get('txnList', {}).get('txnDate')
                    if "T" in txn_date_str:
                        txn_date = datetime.datetime.fromisoformat(
                            txn_date_str)  # Works for '2025-02-03T17:04:00+05:04'
                    else:
                        txn_date = datetime.datetime.strptime(txn_date_str,
                                                              "%Y%m%d%H%M%S")  # Fallback for expected format

                    txn_date_formatted = txn_date.strftime("%d/%m/%Y %I:%M %p")

                    bill_date = datetime.datetime.today().date()  # Fix: Get today's date correctly
                    bill_number = 'xxxxxxxxxx'
                    bill_period = 'NA'

                    bill_fetch_response = bbps_response.bbps_bill_fetch_response.get('billFetchResponse', {}).get(
                        'billerResponse', {})
                    if bill_fetch_response:
                        bill_date = bill_fetch_response.get('billDate', bill_date)
                        bill_number = bill_fetch_response.get('billNumber', bill_number)
                        bill_period = bill_fetch_response.get('bill_period', bill_period)

                    report_data = {
                        'Retailer Name/Contact Number': f"{retailer.pu_name} / {retailer.pu_contact_no}",
                        'Consumer Name/Contact Number': f"{xml.get('transactionStatusResp', {}).get('txnList', {}).get('respCustomerName')} / {xml.get('transactionStatusResp', {}).get('txnList', {}).get('mobile')}",
                        'Transaction Date': txn_date_formatted,
                        'Transaction ID': xml.get('transactionStatusResp', {}).get('txnList', {}).get('payRequestId'),
                        'Biller Name': biller_name,
                        'Biller ID': xml.get('transactionStatusResp', {}).get('txnList', {}).get('billerId'),
                        'Consumer Account Number': 'xxxxxxxxxxxx',
                        'Bill Date': bill_date,
                        'Payment Reference ID': xml.get('transactionStatusResp', {}).get('txnList', {}).get(
                            'payRequestId'),
                        'BBPS Transaction Reference ID': xml.get('transactionStatusResp', {}).get('txnList', {}).get(
                            'txnReferenceId'),
                        'Payment Mode': 'Cash',
                        'Amount': bbps_response.bbps_amount,
                        'Customer Convenience Fee': xml.get('transactionStatusResp', {}).get('txnList', {}).get(
                            'custConvFee'),
                        'Total Amount': bbps_response.bbps_amount,
                        'Bill Number': bill_number,
                        'Bill Period': bill_period,
                        'Payment Method': 'Cash'
                    }
                    return Response({'status': 'success', 'message': 'Transaction status retrieved.',
                                     'data': {'results': report_data}}, status=status.HTTP_200_OK)

                else:
                    return Response({'status': 'fail', 'message': xml}, status=status.HTTP_400_BAD_REQUEST)

            else:
                return Response({'status': 'fail', 'message': xml}, status=status.HTTP_400_BAD_REQUEST)

        except BBPSBillPayment.DoesNotExist:
            return Response({'status': 'fail', 'message': 'Request ID not found.'}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({'status': 'fail', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_bbps_biller_transaction_list(self, request):
        page_number = request.data.get('page_number', 1)
        page_size = request.data.get('page_size', 10)
        transaction_data = request.data.get('transaction_data')
        search = request.data.get('search', '')

        try:
            if not page_number:
                return Response({'status': 'fail', 'message': 'page_number is required.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not transaction_data:
                return Response({'status': 'fail', 'message': 'transaction_data is required.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if not isnumber(page_number):
                return Response({'status': 'fail', 'message': 'page_number must contain only digits.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not isboolean(transaction_data):
                return Response({'status': 'fail', 'message': 'transaction_data must contain only boolen.'},
                                status=status.HTTP_400_BAD_REQUEST)

            page_number = int(page_number)
            page_size = int(page_size)

            if page_number < 1 or page_size < 1:
                return Response({'status': 'fail', 'message': 'page_number and page_size must be greater than 0.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if transaction_data != 'True':
                return Response({'status': 'fail', 'message': 'transaction_data must be true.'},
                                status=status.HTTP_400_BAD_REQUEST)
            try:
                fetch_info = BBPSBillPayment.objects.exclude(bbps_status__in=['PENDING', 'BILL_FETCHED']).filter(
                    created_by=request.user.id
                ).order_by('-pk')

                if search != '':
                    fetch_info = fetch_info.filter(
                        Q(bbps_blr_id__icontains=search) | Q(bbps_trn_unique_id__icontains=search) | Q(
                            bbps_contact_no__icontains=search) | Q(
                            bbps_category__category_name__icontains=search)).order_by('-pk')

                if not fetch_info.exists():
                    return Response({'status': 'success', 'message': 'Biller transaction not found.'},
                                    status=status.HTTP_404_NOT_FOUND)

                paginator = Paginator(fetch_info, page_size)
                page = paginator.get_page(page_number)
                serializer = BBPSBillerPaymentSerializer(page, many=True)
                for data in serializer.data:
                    category = BBPSBiller.objects.get(bbps_blr_id=data['bbps_blr_id'])
                    data['category'] = category.bbps_category.category_name
                    # Convert to datetime if it's a string
                    if isinstance(data['created_at'], str):
                        data['created_at'] = datetime.datetime.strptime(data['created_at'], "%Y-%m-%dT%H:%M:%S.%fZ")

                    data['created_at'] = data['created_at'].strftime("%d-%m-%Y %I:%M %p")

                data = {
                    'total_pages': paginator.num_pages,
                    'current_page': page.number,
                    'total_items': paginator.count,
                    'results': serializer.data
                }

                return Response({'status': 'success', 'message': 'Biller transaction list.', 'data': data},
                                status=status.HTTP_200_OK)
            except BBPSBillPayment.DoesNotExist:
                return Response({'status': 'fail', 'message': 'Biller transaction not found.'},
                                status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BbpsBillerInfoEntryAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAdmin]

    def post(self, request):
        info = request.data.get('info')
        print('===============------------------=')
        json_data = {}
        try:
            print('------------------------------------------------------------------')
            all_bbps_biller = BBPSBiller.objects.filter(is_deleted=False, is_deactive=False).values_list('bbps_blr_id',
                                                                                                         flat=True)
            print('all_bbps_biller', all_bbps_biller)
            data_list = list(all_bbps_biller)
            print('data_list', data_list)
            chunk_size = 2000
            chunks = [data_list[i:i + chunk_size] for i in range(0, len(data_list), chunk_size)]
            print('chunks', chunks)
            for chunk in chunks:
                print('chunk', chunk)
                root = Element('billerInfoRequest')
                for bbps_blr_id in chunk:
                    SubElement(root, 'billerId').text = bbps_blr_id
                print('root', root)
                raw_xml = tostring(root, encoding='utf-8')
                pretty_xml = parseString(raw_xml).toprettyxml(indent="  ")
                encrypted_hex = encrypt_data(pretty_xml)

                url = "https://api.billavenue.com/billpay/extMdmCntrl/mdmRequestNew/xml"
                params = {
                    "accessCode": "AVVK43CB13NO66SBFK",
                    "requestId": "TEST000MNPREQ0000000000000000000042",
                    "ver": "1.0",
                    "instituteId": "MS76",
                }

                response = requests.post(url, params=params, data=encrypted_hex, headers={"Content-Type": "text/plain"})
                response.raise_for_status()

                encrypted_response = response.text
                decrypted_text = decrypt_data(encrypted_response)

                # Convert XML to JSON and ensure proper handling
                dict_data = xmltodict.parse(decrypted_text)
                json_data = json.loads(json.dumps(dict_data))  # Ensure it's a dictionary

                for data in json_data["billerInfoResponse"]["biller"]:
                    BBPSBillResponse.objects.create(
                        bbps_biller_id=data["billerId"],
                        bbps_biller_response=json.dumps(data)  # Save as a JSON string
                    )
            print('=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=')
            return Response({'status': 'success', 'data': 'Data inserted successfully.......................'},
                            status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': f'Internal server error: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def encrypt_data(xml_data):
    print('xml_data', xml_data)
    try:
        key = "13D6751278DC844724FB7A5AC512276E"
        key = binascii.unhexlify(hashlib.md5(key.encode()).hexdigest())
        init_vector = bytes(
            [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f])

        cipher = AES.new(key, AES.MODE_CBC, init_vector)
        plain_text_padded = pad(xml_data.encode(), AES.block_size)
        encrypted_text = cipher.encrypt(plain_text_padded)
        encrypted_hex = binascii.hexlify(encrypted_text).decode()

        return encrypted_hex

    except Exception as e:
        raise Exception(f"Encryption error: {str(e)}")


def decrypt_data(string_data):
    try:
        key = "13D6751278DC844724FB7A5AC512276E"
        key = binascii.unhexlify(hashlib.md5(key.encode()).hexdigest())
        init_vector = bytes(
            [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f])

        encrypted_text_bytes = binascii.unhexlify(string_data)
        cipher = AES.new(key, AES.MODE_CBC, init_vector)
        decrypted_text_padded = cipher.decrypt(encrypted_text_bytes)
        decrypted_text = unpad(decrypted_text_padded, AES.block_size).decode()

        return decrypted_text

    except Exception as e:
        raise Exception(f"Decryption error: {str(e)}")


def xml_to_json(xml_data):
    try:
        dict_data = xmltodict.parse(xml_data)
        return json.dumps(dict_data, indent=4)
    except Exception as e:
        raise Exception(f"XML to JSON conversion error: {str(e)}")


# ====================> Biller Category And Biller Info Add By excel file

# Biller Category excel file Import API
@api_view(['POST'])
def biller_cat_file(request):
    try:

        file = request.FILES['excel_file']

        decoded_file = file.read().decode('utf-8').splitlines()
        csv_reader = csv.reader(decoded_file)

        next(csv_reader)

        for row in csv_reader:
            BBPSBillerCategory.objects.create(
                category_name=row[1],
                is_deleted=(row[2].strip().lower() == 't'),
                is_deactive=(row[3].strip().lower() == 't')
            )

        return Response({'status': 'success', 'message': 'Data imported successfully.'}, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response(
            {'status': 'error', 'message': f'Internal server error: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# Biller File Add API
@api_view(['POST'])
def biller_file(request):
    try:
        file = request.FILES.get('excel_file')
        if not file:
            return Response(
                {'status': 'error', 'message': 'No file provided.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        decoded_file = file.read().decode('utf-8').splitlines()
        csv_reader = csv.reader(decoded_file)

        next(csv_reader)

        for row_index, row in enumerate(csv_reader, start=2):
            print('row--------', row[1])
            try:
                print('---------')
                bbps_biller_id = row[0].strip()
                bbps_blr_id = row[1].strip()
                bbps_blr_name = row[2].strip()
                is_deleted = row[3].strip().lower() == 't' if len(row) > 3 else False
                is_deactive = row[4].strip().lower() == 't' if len(row) > 4 else False
                created_at = row[5].strip()
                updated_at = row[6].strip()
                bbps_category_id = row[7].strip()
                print('=-==-=-=-=-=-=-', bbps_category_id)
                bbps_category = None
                if bbps_category_id:
                    bbps_category = BBPSBillerCategory.objects.get(bbps_id=bbps_category_id)
                    print('bbps_category---', bbps_category)

                BBPSBiller.objects.update_or_create(
                    bbps_biller_id=bbps_biller_id,
                    defaults={
                        'bbps_blr_id': bbps_blr_id,
                        'bbps_blr_name': bbps_blr_name,
                        'is_deleted': is_deleted,
                        'is_deactive': is_deactive,
                        'bbps_category': bbps_category,
                        'created_at': created_at,
                        'updated_at': updated_at,
                    },
                )
            except Exception as row_error:
                return Response(
                    {
                        'status': 'error',
                        'message': f"Error processing row {row_index}: {str(row_error)}",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response({'status': 'success', 'message': 'Data imported successfully.'}, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response(
            {'status': 'error', 'message': f'Internal server error: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )







