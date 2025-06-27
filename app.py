from flask import Flask, render_template, request, send_file
from bs4 import BeautifulSoup
import pandas as pd
import re
import os
import tempfile

app = Flask(__name__)

KEY_COLUMNS = ["Ημερομηνία", "Αιτιολογία", "Ημ/νία Αξίας", "Πίστωση", "Χρέωση", "Υπόλοιπο"]

def extract_account_number(soup):
    possible_texts = []
    for el in soup.find_all(text=re.compile("Αριθμός")):
        parent = el.parent
        text = parent.get_text(separator=" ", strip=True)
        match = re.search(r'\b\d{13}\b', text)
        if match:
            return match.group()
        next_sibling = parent.find_next_sibling()
        if next_sibling:
            match = re.search(r'\b\d{13}\b', next_sibling.get_text())
            if match:
                return match.group()
        possible_texts.append(text)
    all_text = soup.get_text(separator=" ", strip=True)[300:]
    match = re.search(r'\b\d{13}\b', all_text)
    if match:
        return match.group()
    match = re.search(r'\b\d{13,}\b', all_text)
    if match:
        return match.group()
    match = re.search(r'GR\d{2}\s?\d+', all_text)
    if match:
        return match.group()
    return "Λογαριασμός"

def is_transaction_table(headers):
    return headers and all(any(col in h for h in headers) for col in KEY_COLUMNS)

def extract_transaction_tables(html_path):
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")
    tables = soup.find_all("table")
    found = []
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [th.get_text(strip=True) for th in rows[0].find_all("th")]
        if is_transaction_table(headers):
            data = []
            for row in rows[1:]:
                cols = row.find_all(["td", "th"])
                if len(cols) == len(headers):
                    data.append([col.get_text(separator=' ', strip=True) for col in cols])
            df = pd.DataFrame(data, columns=headers)
            found.append(df)
    return found

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        files = request.files.getlist("html_files")
        if not files:
            return "Δεν βρέθηκαν αρχεία.", 400
        all_tables = {}
        for file in files:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.html') as tmp:
                file.save(tmp.name)
                tmp.close()
                with open(tmp.name, "r", encoding="utf-8") as f:
                    soup = BeautifulSoup(f, "html.parser")
                account_number = extract_account_number(soup)
                found = extract_transaction_tables(tmp.name)
                if found:
                    df = pd.concat(found, ignore_index=True)
                    for col in ["Πίστωση", "Χρέωση", "Υπόλοιπο"]:
                        if col in df.columns:
                            df[col] = df[col].str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
                            df[col] = pd.to_numeric(df[col], errors="coerce")
                    base_name = account_number[:28]
                    sheet_name = base_name
                    suffix = 2
                    while sheet_name in all_tables:
                        sheet_name = f"{base_name}_{suffix}"
                        suffix += 1
                    all_tables[sheet_name] = df
                os.unlink(tmp.name)
        if not all_tables:
            return "Δεν βρέθηκαν πίνακες κινήσεων!", 400
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_excel:
            with pd.ExcelWriter(tmp_excel.name) as writer:
                for name, df in all_tables.items():
                    df.to_excel(writer, sheet_name=name, index=False)
            tmp_excel.close()
            return send_file(tmp_excel.name, as_attachment=True, download_name="movements.xlsx")
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)
