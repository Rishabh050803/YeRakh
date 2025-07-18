import requests,mimetypes

# Replace with your actual signed URL (shortened for clarity)
signed_url = "https://storage.googleapis.com/cloud-vault-storage/8bef0ef0-a0aa-4f53-9837-e699abc9060d/8bef0ef0-a0aa-4f53-9837-e699abc9060d_ecd9518e-8dd2-4f54-a9e0-9710f4b63a8f_income.jpg?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=gcs-signer%40cloudvault-466209.iam.gserviceaccount.com%2F20250718%2Fauto%2Fstorage%2Fgoog4_request&X-Goog-Date=20250718T053816Z&X-Goog-Expires=300&X-Goog-SignedHeaders=content-type%3Bhost&X-Goog-Signature=9ae3a36e9afa4c4f5774c531e2f872ca01bf43d6fb71689abc822d0d6a46cd6eefa27dc17377eeed9220d7519e14e584d5cb6805dcbb65bfef7b2c377c26d671763d2cb5684143f35a2248fffbb3a144e95cb3013b560fc49e9af4a5b476539c98295877c7dece1ae7fe375cdecabb78f7e79ecd154516490c8ea8820b0b882a1c614ae59612ad01ad8d8b855509f42b9ae7557a0b5eb81e305ddc495fed153e5628b607c4ba1524193439fdd2347acec7d06e784eba0b6c2f192574fc67bf9f866d73037265b9036fa3a74d28b299386dd0aa588fa6a2fedbc3b4e13f8af16ddd18a54e406421426489f4aa095de6b011944b322825e858c413644f1c0ae05c"

# Local file to upload
file_path = "/home/rishabh/Downloads/income.jpg"
content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

headers = {
    "Content-Type": content_type  # Use the same content type used during URL generation
}

with open(file_path, "rb") as f:
    response = requests.put(signed_url, data=f, headers=headers)

if response.status_code == 200:
    print("✅ File uploaded successfully.")
else:
    print("❌ Upload failed.")
    print("Status Code:", response.status_code)
    print("Response:", response.text)
