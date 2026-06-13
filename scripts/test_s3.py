import requests
from aps_utils import get_internal_token, BUCKET_KEY
token = get_internal_token()
print("Token length:", len(token))
url = f"https://developer.api.autodesk.com/oss/v2/buckets/{BUCKET_KEY}/objects/test.dxf/signeds3upload"
res = requests.get(url, headers={'Authorization': f'Bearer {token}'})
print(res.status_code, res.text)
