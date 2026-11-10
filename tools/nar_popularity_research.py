"""Free official NAR CSV historical popularity exploration. No betting, no API key."""
import argparse
from urllib.request import urlopen, Request
import zipfile, io, csv, collections

URL="https://www.keiba.go.jp/KeibaWeb/DataDownload/RaceDataDownload?type=monthly&k_year=2026&k_month=10"
def inspect():
    req=Request(URL,headers={"User-Agent":"Mozilla/5.0 (NAR research)"})
    with urlopen(req,timeout=75) as r:
        data=r.read()
        print("HTTP",r.status,r.headers.get("Content-Type"),"size",len(data),"first",data[:20],flush=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for member in z.infolist()[:18]:
            data=z.read(member.filename)[:350]
            print("ZIP",member.filename,member.file_size,flush=True)
            if member.filename.endswith(("_horselist.csv","_racelist.csv")):
                rows=csv.DictReader(io.StringIO(z.read(member.filename).decode("utf-8-sig")))
                print("HEADERS",member.filename,rows.fieldnames,flush=True)
                print("FIRST",next(rows),flush=True)
if __name__ == "__main__":
    inspect()
