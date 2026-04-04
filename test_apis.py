import os, sys
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

import urllib.request, json

def test_eia():
    key = os.environ.get('EIA_API_KEY', '')
    if not key:
        print("[EIA] FAIL - EIA_API_KEY not found in .env")
        return False
    url = f"https://api.eia.gov/v2/petroleum/pri/spt/data/?api_key={key}&frequency=daily&data[0]=value&facets[series][]=RWTC&length=3&sort[0][column]=period&sort[0][direction]=desc"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        records = data.get('response', {}).get('data', [])
        if records:
            print(f"[EIA] SUCCESS - {len(records)} records returned:")
            for r in records:
                print(f"  {r['period']} | WTI spot = ${r['value']}")
            return True
        else:
            print(f"[EIA] FAIL - API responded but no data. Response: {json.dumps(data)[:200]}")
            return False
    except Exception as e:
        print(f"[EIA] FAIL - {e}")
        return False

def test_fred():
    key = os.environ.get('FRED_API_KEY', '')
    if not key:
        print("[FRED] FAIL - FRED_API_KEY not found in .env")
        return False
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id=DCOILWTICO&api_key={key}&file_type=json&limit=3&sort_order=desc"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        obs = data.get('observations', [])
        if obs:
            print(f"[FRED] SUCCESS - {len(obs)} observations returned:")
            for o in obs:
                print(f"  {o['date']} | WTI spot = ${o['value']}")
            return True
        else:
            print(f"[FRED] FAIL - API responded but no observations. Response: {json.dumps(data)[:200]}")
            return False
    except Exception as e:
        print(f"[FRED] FAIL - {e}")
        return False

def test_ib_tws():
    try:
        from ib_insync import IB
    except ImportError:
        print("[IB TWS] SKIPPED - ib_insync not installed. Run: pip install ib_insync")
        print("[IB TWS] Will test with raw socket connection instead...")
        return test_ib_socket()

    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=99, timeout=10)
        if ib.isConnected():
            print("[IB TWS] SUCCESS - Connected to TWS on localhost:7497 (paper trading)")
            # Try a quick market data request
            from ib_insync import Future
            cl = Future('CL', exchange='NYMEX')
            contracts = ib.qualifyContracts(cl)
            if contracts:
                print(f"  CL contract found: {contracts[0]}")
            else:
                print("  (Could not qualify CL contract - may need market data subscription)")
            ib.disconnect()
            return True
        else:
            print("[IB TWS] FAIL - connect() returned but isConnected() is False")
            return False
    except Exception as e:
        err = str(e)
        if "actively refused" in err or "No connection" in err or "timed out" in err:
            # Try live port
            try:
                ib.connect('127.0.0.1', 7496, clientId=99, timeout=10)
                if ib.isConnected():
                    print("[IB TWS] SUCCESS - Connected to TWS on localhost:7496 (live trading)")
                    ib.disconnect()
                    return True
            except Exception as e2:
                pass
            print("[IB TWS] FAIL - Could not connect on port 7497 (paper) or 7496 (live)")
            print("  Make sure TWS Desktop is running with API enabled")
            print(f"  Error: {err}")
            return False
        else:
            print(f"[IB TWS] FAIL - {e}")
            return False

def test_ib_socket():
    """Fallback: test raw TCP connection to TWS ports"""
    import socket
    for port in [7497, 7496]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect(('127.0.0.1', port))
            s.close()
            label = "paper" if port == 7497 else "live"
            print(f"[IB TWS] SUCCESS - Port {port} ({label}) is open and accepting connections")
            return True
        except Exception:
            continue
    print("[IB TWS] FAIL - Neither port 7497 (paper) nor 7496 (live) is responding")
    print("  Make sure TWS Desktop is running with API enabled:")
    print("  File > Global Configuration > API > Settings > Enable ActiveX and Socket Clients")
    return False

if __name__ == '__main__':
    print("=" * 60)
    print("  Oil Super Spike Analyzer - API Connection Tests")
    print("=" * 60)
    print()

    results = {}
    results['EIA'] = test_eia()
    print()
    results['FRED'] = test_fred()
    print()
    results['IB TWS'] = test_ib_tws()
    print()

    print("=" * 60)
    print("  RESULTS SUMMARY")
    print("=" * 60)
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        icon = "+" if ok else "X"
        print(f"  [{icon}] {name}: {status}")
    print()

    if all(results.values()):
        print("All tests passed! Ready to start building.")
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"Failed: {', '.join(failed)}. See details above.")
    
    sys.exit(0 if all(results.values()) else 1)
