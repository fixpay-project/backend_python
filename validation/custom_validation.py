import re


def isnumber(number):
    try:
        int(number)
        return True
    except ValueError:
        return False
    except Exception:
        return False
    
def isfloat(number):
    try:
        float(number)
        return True
    except ValueError:
        return False
    
def checkbannertype(banner_type):
    try:
        if banner_type == 'WEB BANNER' or banner_type == 'MOBILE BANNER' or banner_type == 'LOGIN PAGE BANNER':
            return True

        else:
            return False

    except Exception:
        return False


def validate_mobile_number(mobile_number):
    pattern = re.fullmatch('[6-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]',mobile_number)
    if pattern:
        return True
    else:
        return False


def validation_email_address(email):
    valid = re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email)
    if valid:
        return True
    else:
        return False


def isstring(string):
    # Ensure that only alphabetic characters or spaces (not other whitespace) are allowed
    return all(char.isalpha() or char == ' ' or char == '_' for char in string)

def isboolean(value):
    if value in ['true', 'TRUE', 'True', '1']:
        return True
    elif value in ['false', 'FALSE', 'False', '0']:
        return False
    else:
        return None

def checkpancardvalidation(pan_card):
    pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]$'
    check_pan_card = re.match(pattern, pan_card)
    if check_pan_card:
        return True
    else:
        return False


def is_valid_ifsc(ifsc_code):
    pattern = r'^[A-Z]{4}0[A-Z0-9]{6}$'
    
    if re.match(pattern, ifsc_code):
        return True
    else:
        return False

def validate_account_number(account_number):

    pattern = r"^\d{11,16}$"  # Matches 8-16 digits
    if re.match(pattern, account_number):
        return True
    else:
        return False

