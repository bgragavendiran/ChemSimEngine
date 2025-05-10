import os
import json
import firebase_admin
from firebase_admin import credentials, storage, db
from firebase_admin import delete_app
from omni.kit.app import get_app

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
cred_path = os.path.join(BASE_DIR, "firebase-adminsdk.json")

# (Re)init Firebase safely
if firebase_admin._apps:
    print("🔄 Reinitializing Firebase app...")
    delete_app(firebase_admin.get_app())
cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred, {
    "storageBucket": "vrchemlab-d3f91.firebasestorage.app",
    "databaseURL": "https://vrchemlab-d3f91-default-rtdb.asia-southeast1.firebasedatabase.app"
})
bucket = storage.bucket("vrchemlab-d3f91.firebasestorage.app")
print("✅ Firebase bucket in use:", bucket.name)
print("✅ Bucket exists?", bucket.exists())

def upload_anim_and_update_db(local_path, folder, reaction_id, reaction_summary):
    file_name = os.path.basename(local_path)
    blob_path = f"animations/{folder}/{file_name}"

    ref = db.reference(f"reaction_anim_urls/{reaction_id}")
    existing_data = ref.get()
    if existing_data and existing_data.get("file_name") == file_name:
        return True, existing_data.get("download_url", "Already uploaded")

    try:
        blob = bucket.blob(blob_path)
        blob.upload_from_filename(local_path)
        blob.make_public()
        download_url = blob.public_url
        ref.set({
            "file_name": file_name,
            "firebase_path": blob_path,
            "download_url": download_url,
            "reaction": reaction_summary.get("reaction", ""),
            "reactionDescription": reaction_summary.get("reactionDescription", "")
        })
        return True, download_url
    except Exception as e:
        return False, str(e)

def get_firebase_reactions_ref():
    return db.reference("reactions")

def get_firebase_compounds_ref():
    return db.reference("compounds")

ANIM_LOCAL_DIR = os.path.join(BASE_DIR, "output_usd")

def _get_cached_upload_status():
    ref = db.reference("reaction_anim_urls")
    return ref.get() or {}

def sync_missing_animations():
    print("🔍 Scanning for missing animations to upload...")
    if not os.path.exists(ANIM_LOCAL_DIR):
        print("⚠️ No animations directory found.")
        return

    uploaded_map = _get_cached_upload_status()
    files_to_upload = []
    for folder in os.listdir(ANIM_LOCAL_DIR):
        folder_path = os.path.join(ANIM_LOCAL_DIR, folder)
        if not os.path.isdir(folder_path):
            continue
        expected_file = uploaded_map.get(folder, {}).get("file_name")
        for file in os.listdir(folder_path):
            if file.endswith(".usd") and file.startswith("reaction_anim_") and file != expected_file:
                full_path = os.path.join(folder_path, file)
                files_to_upload.append((folder, file, full_path))

    print(f"📦 Found {len(files_to_upload)} missing animations to upload.")
    for idx, (folder, file_name, full_path) in enumerate(files_to_upload, start=1):
        print(f"📄 [{idx}/{len(files_to_upload)}] Uploading: {file_name} → {full_path}")
        reaction_summary = {
            "reactionName": folder,
            "reactionDescription": f"Auto-synced reaction {folder}"
        }

        # Try to enrich metadata from corresponding JSON
        json_path = os.path.join(BASE_DIR, "output_json", f"{folder}.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    reaction_summary["reaction"] = data.get("reaction", folder)
                    reaction_summary["reactionDescription"] = data.get("reactionDescription", f"Reaction: {folder}")
            except Exception as e:
                print(f"⚠️ Could not read {folder}.json: {e}")

        success, msg = upload_anim_and_update_db(full_path, folder, folder, reaction_summary)
        if success:
            print(f"✅ Uploaded: {msg}")
        else:
            print(f"❌ Upload failed: {msg}")

def start_background_sync():
    def _sync():
        import threading
        thread = threading.Thread(target=sync_missing_animations, daemon=True)
        thread.start()