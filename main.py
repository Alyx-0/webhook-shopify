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
        
        # Safely get customer email
        customer = order.get('customer')
        customer_email = customer.get('email', '') if customer else ''
        
        rows = []
        for i, item in enumerate(order.get('line_items', [])):
            row = [
                order.get('name', ''),
                order.get('email', ''),
                order.get('financial_status', ''),
                order.get('processed_at', ''),
                order.get('fulfillment_status', ''),
                "fullfilled at",
                order.get('buyer_accepts_marketing', ''),
                order.get('currency', ''),
                order.get('subtotal_price', ''),
                order.get('total_shipping_price_set', {}).get('presentment_money', {}).get('amount'),
                order.get('total_tax', ''),
                order.get('total_price', ''),
                order.get('discount_codes', []),
                order.get('shipping_lines', []),
                order.get('created_at', ''),
                item.get('quantity', ''),
                item.get('name', ''),
                item.get('price', ''),
                item.get('sku', ''),
                item.get('requires_shipping', ''),
                item.get('taxable', ''),
                item.get('fulfillment_status', ''),
                order.get('billing_address', {}).get('name', ''),
                order.get('billing_address', {}).get('address1', ''),
                order.get('billing_address', {}).get('address1', ''),
                order.get('billing_address', {}).get('address2', ''),
                order.get('billing_address', {}).get('company', ''),
                order.get('billing_address', {}).get('city', ''),
                order.get('billing_address', {}).get('zip', ''),
                order.get('billing_address', {}).get('province_code', ''),
                order.get('billing_address', {}).get('country_code', ''),
                order.get('billing_address', {}).get('phone', ''),
                order.get('shipping_address', {}).get('name', ''),
                order.get('shipping_address', {}).get('address1', ''),
                order.get('shipping_address', {}).get('address1', ''),
                order.get('shipping_address', {}).get('address2', ''),
                order.get('shipping_address', {}).get('company', ''),
                order.get('shipping_address', {}).get('city', ''),
                order.get('shipping_address', {}).get('zip', ''),
                order.get('shipping_address', {}).get('province_code', ''),
                order.get('shipping_address', {}).get('country_code', ''),
                order.get('shipping_address', {}).get('phone', ''),
                order.get('note', ''),
                "empty",
                order.get('cancelled_at', ''),
                "Payment Method",
                "Payment Reference",
                "Refunded Amount",
                order.get('vendor', ''),
                order.get('total_outstanding', ''),
                "Employee",
                "Location",
                "Device ID",
                "Id",
                order.get('tags', ''),
                "Risk Level",
                "Source",
                item.get('total_discount', ''),
                "", #Tax 1 Name
                "", #Tax 1 Value
                "", #Tax 2 Name
                "", #Tax 2 Value
                "", #Tax 3 Name
                "", #Tax 3 Value
                "", #Tax 4 Name
                "", #Tax 4 Value
                "", #Tax 5 Name
                "", #Tax 5 Value
                order.get('phone', ''),
                "Receipt Number",
                "Duties",
                order.get('billing_address', {}).get('province', ''),
                order.get('shipping_address', {}).get('province', ''),
                "Payment ID",
                order.get('payment_terms', ''),
                "Next Payment Due At",
                "Payment References",
                "Business Entity Name",
                order.get('merchant_business_entity_id', '')
            ]
            rows.append(row)
        
        if rows:
            body = {'values': rows}
            sheets_client.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{SHEET_NAME}!A:H",
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            print(f"✅ Appended {len(rows)} rows")
        
    except Exception as e:
        print(f"❌ Error: {e}")

# ========== ORDER PROCESSING ==========
def process_order(order: dict):
    """Process the order data"""
    print(f"\n📦 Processing order: {order.get('name', 'Unknown')}")
    
    # Safely get customer data
    customer = order.get('customer')
    if customer is None:
        customer_email = "No customer (test order)"
    else:
        customer_email = customer.get('email', 'Unknown')
    
    print(f"   Customer: {customer_email}")
    print(f"   Total: ${order.get('total_price', '0')}")
    print(f"   Items: {len(order.get('line_items', []))}")
    
    # Append to Google Sheets
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