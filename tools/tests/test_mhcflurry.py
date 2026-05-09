#!/usr/bin/env python3
"""MHCflurry 批量测试 — 使用 data/function.csv 真实肽数据"""
import json, sys, time
from datetime import datetime, timezone
from pathlib import Path
import httpx
import pandas as pd

SERVICE = "mhcflurry"
PORT = 8005
BASE_URL = f"http://127.0.0.1:{PORT}"
DATA_PATH = Path(__file__).parents[2] / "data" / "function.csv"
RESULTS_DIR = Path(__file__).parent / "results"
OUT_PATH = RESULTS_DIR / f"{SERVICE}_batch_test.json"
BATCH_N = 20
TIMEOUT = 120

def load_peptides(n):
    df = pd.read_csv(DATA_PATH)
    df = df[df["is_antioxidant"] == 1].copy()
    df["_len"] = df["sequence"].str.len()
    df = df[(df["_len"] >= 5) & (df["_len"] <= 15)]
    df = df.head(n)
    peptides = []
    for _, row in df.iterrows():
        seq = str(row["sequence"]).strip().upper()
        pid = row.get("source_name", "")
        if pd.isna(pid) or str(pid).strip() == "":
            pid = row.get("database_id", "")
        if pd.isna(pid) or str(pid).strip() == "":
            pid = seq
        peptides.append({"sequence": seq, "peptide_id": str(pid)})
    return peptides

def check_health(client):
    resp = client.get(f"{BASE_URL}/health", timeout=10)
    resp.raise_for_status()
    return resp.json()

def check_info(client):
    resp = client.get(f"{BASE_URL}/info", timeout=10)
    resp.raise_for_status()
    return resp.json()

def predict_single(client, peptide):
    resp = client.post(f"{BASE_URL}/predict", json=peptide, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()

def predict_batch(client, peptides):
    resp = client.post(f"{BASE_URL}/predict/batch", json={"sequences": peptides}, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()

def save(result):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nSaved: {OUT_PATH}")

def main():
    print(f"=== {SERVICE} Batch Test ===")
    result = {"service": SERVICE, "tested_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    with httpx.Client(timeout=TIMEOUT) as client:
        print("[1/4] Health check ...")
        try:
            result["health"] = check_health(client)
            print(f"  status={result['health'].get('status')}, loaded={result['health'].get('model_loaded')}")
        except Exception as e:
            result["health"] = {"error": str(e)}
            result["summary"] = f"FAIL: {e}"
            save(result)
            return 1
        print("[2/4] Info ...")
        try:
            result["info"] = check_info(client)
        except Exception as e:
            result["info"] = {"error": str(e)}
        print("[3/4] Single predict ...")
        peptides = load_peptides(BATCH_N)
        try:
            result["single_predict"] = predict_single(client, peptides[0])
            r = result["single_predict"]
            if r.get("success"):
                print(f"  {peptides[0]['sequence']}: score={r['result']['score']}, label={r['result']['label']}")
        except Exception as e:
            result["single_predict"] = {"error": str(e)}
        print(f"[4/4] Batch predict ({len(peptides)} peptides) ...")
        t0 = time.time()
        try:
            result["batch_predict"] = predict_batch(client, peptides)
            result["batch_predict"]["_elapsed_seconds"] = round(time.time() - t0, 1)
            bp = result["batch_predict"]
            print(f"  success={bp.get('success')}, total={bp.get('total')}, elapsed={result['batch_predict']['_elapsed_seconds']}s")
            for r in bp.get("results", []):
                print(f"    {r['peptide_id']}: {r['score']:.4f} [{r['label']}]")
        except Exception as e:
            result["batch_predict"] = {"error": str(e)}
    bp_ok = result.get("batch_predict", {}).get("success", False)
    health_ok = result.get("health", {}).get("model_loaded", False)
    result["summary"] = "OK" if (health_ok and bp_ok) else ("PARTIAL" if health_ok else "FAIL")
    save(result)
    return 0

if __name__ == "__main__":
    sys.exit(main())
