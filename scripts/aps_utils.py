import os
import requests
import base64
import json

APS_CLIENT_ID = os.environ.get('APS_CLIENT_ID', 'a7SOMReK1gBT6KhMJwK9jjZlRFBXYdbiHrrsoAipVOpInOIt')
APS_CLIENT_SECRET = os.environ.get('APS_CLIENT_SECRET', 'Qgy8OLzGpqpEzf43kKc5xqShFYg7ANWb0df6VcmK3NX5R5zbOqpLoW0RTLrIOJW6')
BUCKET_KEY = 'cyvl_hackathon_bucket_12345' # globally unique

def get_internal_token():
    url = "https://developer.api.autodesk.com/authentication/v2/token"
    auth_str = f"{APS_CLIENT_ID}:{APS_CLIENT_SECRET}"
    auth_b64 = base64.b64encode(auth_str.encode()).decode()
    headers = {
        'Authorization': f'Basic {auth_b64}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {
        'grant_type': 'client_credentials',
        'scope': 'data:read data:write bucket:create bucket:read'
    }
    response = requests.post(url, headers=headers, data=payload)
    if response.status_code == 200:
        return response.json()['access_token']
    else:
        print("Auth Error:", response.text)
        return None

def get_public_token():
    url = "https://developer.api.autodesk.com/authentication/v2/token"
    auth_str = f"{APS_CLIENT_ID}:{APS_CLIENT_SECRET}"
    auth_b64 = base64.b64encode(auth_str.encode()).decode()
    headers = {
        'Authorization': f'Basic {auth_b64}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {
        'grant_type': 'client_credentials',
        'scope': 'data:read'
    }
    response = requests.post(url, headers=headers, data=payload)
    if response.status_code == 200:
        return response.json()
    return None

def create_bucket_if_not_exists(token):
    url = "https://developer.api.autodesk.com/oss/v2/buckets"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    payload = {
        'bucketKey': BUCKET_KEY,
        'policyKey': 'transient'
    }
    res = requests.post(url, headers=headers, json=payload)
    # 200 OK or 409 Conflict (already exists)
    return res.status_code in [200, 409]

def upload_dxf_and_translate(filepath, filename):
    token = get_internal_token()
    if not token:
        return None
        
    create_bucket_if_not_exists(token)
    
    # 1. Get Signed S3 URL
    url = f"https://developer.api.autodesk.com/oss/v2/buckets/{BUCKET_KEY}/objects/{filename}/signeds3upload"
    headers = {
        'Authorization': f'Bearer {token}'
    }
    
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        print("Signed S3 Error:", res.text)
        return None
        
    s3_data = res.json()
    upload_url = s3_data['urls'][0]
    upload_key = s3_data['uploadKey']
    
    # 2. Upload to S3 directly
    with open(filepath, 'rb') as f:
        file_data = f.read()
        
    s3_res = requests.put(upload_url, data=file_data)
    if s3_res.status_code != 200:
        print("S3 Put Error:", s3_res.text)
        return None
        
    # 3. Complete Upload
    complete_headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    complete_payload = {
        "uploadKey": upload_key
    }
    comp_res = requests.post(url, headers=complete_headers, json=complete_payload)
    if comp_res.status_code != 200:
        print("Complete Upload Error:", comp_res.text)
        return None
        
    object_id = comp_res.json()['objectId']
    urn = base64.urlsafe_b64encode(object_id.encode('utf-8')).decode('utf-8').rstrip('=')
    
    # 4. Start Translation Job
    job_url = "https://developer.api.autodesk.com/modelderivative/v2/designdata/job"
    job_headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    job_payload = {
        "input": {
            "urn": urn
        },
        "output": {
            "formats": [
                {
                    "type": "svf",
                    "views": ["2d", "3d"]
                }
            ]
        }
    }
    
    job_res = requests.post(job_url, headers=job_headers, json=job_payload)
    print("Translation Job Triggered:", job_res.status_code, job_res.text)
    
    return urn
