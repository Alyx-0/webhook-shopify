from fastapi import FastAPI, Request, BackgroundTasks
import hmac
import hashlib
import json
import os
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = FastAPI()

# ========== CONFIGURATION ==========
# Get from environment variables (set these on Render/Vercel)
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "")
SHEET_NAME = os.environ.get("SHEET_NAME", "Sheet1")

# ========== GOOGLE SHEETS AUTH ==========
def get_google_sheets_client():
    """Authenticate using service account JSON from environment"""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise Exception("GOOGLE_CREDENTIALS environment variable not set")
    
    creds_dict = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    return build('sheets', 'v4', credentials=creds)

# ========== SHOPIFY WEBHOOK VERIFICATION ==========
def verify_webhook(payload: bytes, signature: str) -> bool:
    """Verify webhook came from Shopify"""
    if not signature or not WEBHOOK_SECRET:
        return True  # Skip verification if no secret (testing)
    
    digest = hmac.new(
        WEBHOOK_SECRET.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(digest, signature)

# ========== GOOGLE SHEETS APPEND ==========
def append_to_sheets(order: dict):
    """Append order data to Google Sheets"""
    print("🔍 STEP 1: append_to_sheets started")
    print(f"🔍 SPREADSHEET_ID: {SPREADSHEET_ID}")
    print(f"🔍 SHEET_NAME: {SHEET_NAME}")
    
    try:
        print("🔍 STEP 2: Getting Google Sheets client...")
        sheets_client = get_google_sheets_client()
        print("✅ STEP 3: Got Google Sheets client")
        
        print("🔍 STEP 4: Building rows...")
        rows = []
        line_items = order.get('line_items', [])
        print(f"🔍 Found {len(line_items)} line items")
        
        for item in line_items:
            row = [
                order.get('name', ''),
                order.get('customer', {}).get('email', ''),
                item.get('title', ''),
                item.get('quantity', 0),
                item.get('price', 0),
                float(item.get('quantity', 0)) * float(item.get('price', 0)),
                order.get('total_price', 0),
                datetime.now().isoformat()
            ]
            rows.append(row)
            print(f"🔍 Row added for: {item.get('title')}")
        
        if rows:
            print(f"🔍 STEP 5: Appending {len(rows)} rows to Google Sheets...")
            body = {'values': rows}
            result = sheets_client.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{SHEET_NAME}!A:H",
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            print(f"✅ STEP 6: Success! Appended {len(rows)} rows")
            print(f"✅ Updated range: {result.get('updates', {}).get('updatedRange')}")
        else:
            print("⚠️ No rows to append")
            
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

# ========== ORDER PROCESSING ==========
def process_order(order: dict):
    """Process order in background"""
    print(f"\n📦 Processing order: {order.get('name', 'Unknown')}")
    print(f"   Customer: {order.get('customer', {}).get('email', 'Unknown')}")
    print(f"   Total: ${order.get('total_price', '0')}")
    print(f"   Items: {len(order.get('line_items', []))}")
    
    append_to_sheets(order)
    
    print(f"✅ Order {order.get('name')} processed!")

# ========== WEBHOOK ENDPOINT ==========
@app.post("/webhook/orders/create")
async def shopify_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_shopify_hmac_sha256: str = None
):
    """Receive Shopify order webhook"""
    
    # Get raw body
    body = await request.body()
    
    # Verify signature (optional, enable for production)
    # if not verify_webhook(body, x_shopify_hmac_sha256):
    #     return {"error": "Invalid webhook signature"}, 401
    
    # Parse order
    try:
        order = await request.json()
        print(f"✅ Received order: {order.get('name', 'Unknown')}")
    except:
        return {"error": "Invalid JSON"}, 400
    
    # Process in background (responds immediately)
    background_tasks.add_task(process_order, order)
    
    return {"status": "ok", "message": "Webhook received"}

# ========== HEALTH CHECK ==========
@app.get("/")
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "Shopify to Google Sheets"}

# ========== FOR LOCAL DEVELOPMENT ==========
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)