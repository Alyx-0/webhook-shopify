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
    try:
        sheets_client = get_google_sheets_client()
        
        rows = []
        for item in order.get('line_items', []):
            row = [
                order.get('name', ''),                    # Order number
                order.get('created_at', ''),              # Date
                order.get('customer', {}).get('email', ''), # Customer email
                item.get('title', ''),                    # Product name
                item.get('quantity', 0),                  # Quantity
                item.get('price', 0),                     # Unit price
                float(item.get('quantity', 0)) * float(item.get('price', 0)),  # Line total
                order.get('total_price', 0),              # Order total
                order.get('financial_status', ''),        # Payment status
                order.get('fulfillment_status', ''),      # Fulfillment status
                datetime.now().isoformat()                # Processed at
            ]
            rows.append(row)
        
        if rows:
            body = {'values': rows}
            sheets_client.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{SHEET_NAME}!A:K",
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            print(f"✅ Appended {len(rows)} rows for order {order.get('name')}")
        else:
            print(f"⚠️ No line items found in order {order.get('name')}")
            
    except Exception as e:
        print(f"❌ Error appending to sheets: {e}")

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