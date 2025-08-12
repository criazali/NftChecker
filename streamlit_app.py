import streamlit as st
import requests
import pandas as pd
import time

# ==== CONFIG ====
output_csv_path = "results.csv"  # Path to save results
timeout = 15
retries = 3
sleep_time = 0.15

SYMBOL_BASE = "https://address-svc-utyjy373hq-uc.a.run.app/symbols"
ADDR_BASE = "https://address-svc-utyjy373hq-uc.a.run.app/v1/networks/eth/addresses"

# ==== FUNCTIONS ====
def fetch_json(url, timeout=15, retries=3, sleep=0.15):
    """GET JSON with retries/backoff."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 404:
                return None, f"404 Not Found: {url}"
            resp.raise_for_status()
            return resp.json(), None
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(sleep * attempt)
    return None, f"Failed after {retries} retries. Last error: {last_err}"

def extract_address_from_symbol_payload(payload):
    if not isinstance(payload, dict):
        return None
    addr = payload.get("address")
    if isinstance(addr, str) and addr:
        return addr
    for key in ("contractAddress", "tokenAddress"):
        addr = payload.get(key)
        if isinstance(addr, str) and addr:
            return addr
    return None

def extract_type_from_address_payload(payload, address=None):
    if not isinstance(payload, dict):
        return None, "Invalid JSON payload (not a dict)"
    if "item" in payload and isinstance(payload["item"], dict):
        ctype = payload["item"].get("type")
        return ctype, None
    if address:
        if address in payload:
            node = payload[address]
        elif address.lower() in payload:
            node = payload[address.lower()]
        else:
            node = None
    else:
        node = None
    if node is None:
        try:
            node = next(iter(payload.values()))
        except StopIteration:
            node = None
    if isinstance(node, dict) and isinstance(node.get("item"), dict):
        ctype = node["item"].get("type")
        return ctype, None
    return None, "Could not locate item.type in address payload"

def classify_ticker(ticker):
    ticker_norm = (ticker or "").strip()
    if not ticker_norm:
        return {
            "ticker": ticker,
            "address": "",
            "contract_type": "",
            "is_nft": "",
            "error": "Empty ticker value",
        }
    # Step 1: symbol lookup
    sym_url = f"{SYMBOL_BASE}/{ticker_norm}"
    sym_payload, err = fetch_json(sym_url, timeout=timeout, retries=retries, sleep=sleep_time)
    if err:
        return {
            "ticker": ticker_norm,
            "address": "",
            "contract_type": "",
            "is_nft": False,
            "error": f"symbol lookup error: {err}",
        }
    address = extract_address_from_symbol_payload(sym_payload)
    if not address:
        return {
            "ticker": ticker_norm,
            "address": "",
            "contract_type": "",
            "is_nft": False,
            "error": "address missing in symbol payload",
        }
    # Step 2: address lookup
    addr_url = f"{ADDR_BASE}/{address}"
    addr_payload, err = fetch_json(addr_url, timeout=timeout, retries=retries, sleep=sleep_time)
    if err:
        return {
            "ticker": ticker_norm,
            "address": address,
            "contract_type": "",
            "is_nft": False,
            "error": f"address lookup error: {err}",
        }
    contract_type, err2 = extract_type_from_address_payload(addr_payload, address)
    if err2:
        return {
            "ticker": ticker_norm,
            "address": address,
            "contract_type": "",
            "is_nft": False,
            "error": err2,
        }
    is_nft = (str(contract_type).lower() == "non-fungible-token") if contract_type else False
    return {
        "ticker": ticker_norm,
        "address": address,
        "contract_type": contract_type or "",
        "is_nft": is_nft,
        "error": "",
    }

# ==== STREAMLIT APP ====
st.title("NFT Ticker Checker")

uploaded_file = st.file_uploader("Upload CSV file with 'ticker' column", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    
    if "ticker" not in df.columns:
        st.error("CSV must contain a 'ticker' column")
    else:
        st.info("Processing tickers... This may take a while for large files.")
        results = []
        progress_bar = st.progress(0)
        
        for idx, ticker in enumerate(df["ticker"], start=1):
            results.append(classify_ticker(ticker))
            progress_bar.progress(idx / len(df))
        
        out_df = pd.DataFrame(results)
        out_df.to_csv(output_csv_path, index=False)

        st.success("Processing complete!")
        st.dataframe(out_df)

        # Download button
        st.download_button(
            label="Download results as CSV",
            data=out_df.to_csv(index=False),
            file_name="results.csv",
            mime="text/csv"
        )
