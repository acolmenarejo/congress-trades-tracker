import json, requests
D="https://data-api.polymarket.com"; G="https://gamma-api.polymarket.com"
def get(u,p): 
    r=requests.get(u,params=p,timeout=30); print("GET",r.url,r.status_code); return r.json()
t=get(f"{D}/trades",{"filterType":"CASH","filterAmount":10000,"limit":500,"takerOnly":"true"})
print(type(t), len(t)); print(json.dumps(t[:2],indent=1)[:2500])
import collections
print("sizes", sorted([round(float(x["size"])*float(x["price"])) for x in t])[-20:])
print("time span", min(x["timestamp"] for x in t), max(x["timestamp"] for x in t))
cids=list({x["conditionId"] for x in t})[:20]
m=get(f"{G}/markets",{"condition_ids":cids,"limit":50})
print(len(m)); print(json.dumps(m[0],indent=1)[:3000])
w=t[0]["proxyWallet"]
a=get(f"{D}/activity",{"user":w,"limit":500})
print("activity", len(a), json.dumps(a[-1],indent=1)[:800] if a else None)
v=get(f"{D}/value",{"user":w}); print("value",v)
tr=get(f"{D}/traded",{"user":w}); print("traded",tr)
