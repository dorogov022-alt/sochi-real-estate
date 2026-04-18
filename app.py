from dotenv import load_dotenv
import os
load_dotenv()




from flask import Flask, render_template, request, url_for
import pandas as pd
import requests
import re
import unicodedata
import html
import time


app = Flask(__name__)
last_request = {}
last_leads = set()




def clean_text(value):
    return str(value).strip()




# ================= SLUG =================
def create_slug(name):
    name = str(name)




    # 1. нижний регистр
    name = name.lower().strip()




    # 2. убрать акценты/юникод мусор
    name = unicodedata.normalize('NFKD', name)




    # 3. оставить только буквы/цифры/пробелы
    name = re.sub(r'[^a-z0-9а-яё\s-]', '', name)




    # 4. пробелы → дефисы
    name = re.sub(r'\s+', '-', name)




    # 5. убрать двойные дефисы
    name = re.sub(r'-+', '-', name)




    return name.strip('-')
def build_slugs(df):
    used_slugs = set()
    slugs = []




    for name in df["Название ЖК"].fillna("").astype(str):


        base_slug = create_slug(name)
        slug = base_slug
        i = 2




        while slug in used_slugs:
            slug = f"{base_slug}-{i}"
            i += 1




        used_slugs.add(slug)
        slugs.append(slug)




    return slugs




# ================= TELEGRAM =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")




# ================= ФОТО =================
def extract_photos(row):
    photos = []




    try:
        for col in row.index:
            if "Фото" in str(col) and pd.notna(row[col]):
                filename = os.path.basename(str(row[col]).strip())
                if filename:
                    photos.append(filename)
    except Exception:
        pass


    return photos




# ================= ЗАГРУЗКА EXCEL =================
try:
    data = pd.read_excel("jk_sochi.xlsx")
except Exception as e:
    print("❌ Ошибка загрузки Excel:", e)
    data = pd.DataFrame()
 
    # ================= LOCATION DATA =================
try:
    loc_data = pd.read_excel("location.xlsx")
except Exception as e:
    print("❌ Ошибка загрузки location.xlsx:", e)
    loc_data = pd.DataFrame()






# slug
if "Название ЖК" in data.columns:
    data["slug"] = build_slugs(data)
else:
    data["slug"] = []




# numeric safety
numeric_cols = ["Цена_мин", "Цена_макс", "Площадь_мин", "Площадь_макс"]




for col in numeric_cols:
    if col in data.columns:
        data[col] = pd.to_numeric(data[col], errors="coerce")




# ================= HOME =================
@app.route("/")
def home():


    district = request.args.get("district", "")
    price_to = request.args.get("price_to", "")
    area_from = request.args.get("area_from", "")
    search = request.args.get("search", "")


    filtered = data.copy()




    if search and "Название ЖК" in filtered.columns:
        filtered = filtered[
            filtered["Название ЖК"].astype(str).str.contains(search, case=False, na=False)
        ]




    if district and "Район" in filtered.columns:
        filtered = filtered[
            filtered["Район"].astype(str).str.contains(district, case=False, na=False)
        ]




    if price_to and "Цена_мин" in filtered.columns:
        try:
            filtered = filtered[filtered["Цена_мин"].fillna(0) <= float(price_to)]
        except:
            pass




    if area_from and "Площадь_макс" in filtered.columns:
        try:
            filtered = filtered[filtered["Площадь_макс"].fillna(0) >= float(area_from)]
        except:
            pass




    filtered = filtered.sort_values("Название ЖК") if "Название ЖК" in filtered.columns else filtered


    complexes = []


    for _, row in filtered.iterrows():
        c = row.to_dict()




        c["photos"] = extract_photos(row)




        c["photo_url"] = [
            url_for("static", filename="images/" + p)
            for p in c["photos"]
        ]


        for col in numeric_cols:
            if col in c and pd.isna(c[col]):
                c[col] = None




        complexes.append(c)




    districts_list = []
    if "Район" in data.columns:
        districts_list = sorted(data["Район"].dropna().unique())




    return render_template(
        "index.html",
        complexes=complexes,
        districts=districts_list
    )




# ================= JK PAGE =================
@app.route("/jk/<slug>")
def jk_page(slug):




    if "slug" not in data.columns:
        return "Slug отсутствует", 500




    jk_row = data[data["slug"] == slug]




    if jk_row.empty:
        return "ЖК не найден", 404




    row = jk_row.iloc[0].to_dict()


    row["photos"] = extract_photos(jk_row.iloc[0])
    row["photo_url"] = [
        url_for("static", filename="images/" + p)
        for p in row["photos"]
    ]




    district = row.get("Район")


    similar_list = []


    if district and "Район" in data.columns:
        similar = data[
            (data["Район"] == district) &
            (data["slug"] != slug)
        ].head(3)




        for _, s in similar.iterrows():
            item = s.to_dict()
            item["photos"] = extract_photos(s)
            item["photo_url"] = [
                url_for("static", filename="images/" + p)
                for p in item["photos"]
            ]
            similar_list.append(item)




    return render_template(
        "jk_page.html",
        jk=row,
        similar=similar_list
    )




# ================= DISTRICTS LIST (НОВЫЙ РОУТ) =================
@app.route("/districts")
def districts():


    if "Район" not in data.columns:
        return "Нет районов", 500


    result = []


    for d in sorted(data["Район"].dropna().astype(str).unique()):


        df = data[data["Район"].astype(str) == d]


        if "Цена_мин" in df.columns:
            prices = pd.to_numeric(df["Цена_мин"], errors="coerce").dropna()
        else:
            prices = pd.Series(dtype=float)


        if len(prices) > 0:
            mean_val = prices.mean()
            avg_price = int(mean_val) if pd.notna(mean_val) else None
        else:
            avg_price = None


        result.append({
            "name": d,
            "slug": create_slug(d),
            "count": len(df),
            "avg_price": avg_price
        })


    return render_template("districts.html", districts=result)






# ================= DISTRICT PAGE =================
@app.route("/district/<slug>")
def district_page(slug):


    if "Район" not in data.columns:
        return "Нет районов в данных", 500


    df = data.copy()
    df = df[df["Район"].astype(str).apply(create_slug) == slug]




    if df.empty:
        return "Район не найден", 404


    complexes = []


    for _, row in df.iterrows():
        c = row.to_dict()


        c["photos"] = extract_photos(row)
        c["photo_url"] = [
            url_for("static", filename="images/" + p)
            for p in c["photos"]
        ]


        complexes.append(c)


    return render_template(
        "district_page.html",
        district=slug,
        complexes=complexes
    )


# ================= LOCATIONS =================
@app.route("/locations")
def locations():


    locations = []


    for _, row in loc_data.iterrows():
        loc = row.to_dict()


        loc["photos"] = extract_photos(row)


        loc["photo_url"] = [
            url_for("static", filename="images/" + p)
            for p in loc["photos"]
        ]


        locations.append(loc)


    return render_template("location.html", locations=locations)






# ================= LEAD =================
@app.route("/lead", methods=["POST"])
def lead():




    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    now = time.time()




    # 🔥 антиспам по IP
    if ip in last_request:
        if now - last_request[ip] < 5:
            return "TOO MANY REQUESTS", 429




    last_request[ip] = now




    # 📥 получаем данные
    name = clean_text(request.form.get("name", ""))
    phone = clean_text(request.form.get("phone", ""))
    message = clean_text(request.form.get("message", ""))




    # 🛑 HONEYPOT (боты заполняют скрытое поле)
    honeypot = request.form.get("website", "")
    if honeypot:
        return "BOT DETECTED", 400




    # 1. проверка пустых данных
    if not name or not phone:
        return "EMPTY", 400




    # 2. проверка имени
    if not re.match(r"^[a-zA-Zа-яА-ЯёЁ\s]{2,50}$", name):
        return "INVALID NAME", 400




    # 3. проверка телефона
    if not re.match(r"^[0-9+\-\s]{7,20}$", phone):
        return "INVALID PHONE", 400




    # 🔥 защита от дублей
    key = f"{phone}:{message}"
    if key in last_leads:
        return "DUPLICATE", 400


    last_leads.add(key)


    # 🛡️ защита от XSS (очистка перед отправкой)
    name = html.escape(name)
    phone = html.escape(phone)
    message = html.escape(message)




    text = f"""
🔥 НОВАЯ ЗАЯВКА


👤 {name}
📞 {phone}
💬 {message}
"""


    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text
            }
        )
    except Exception as e:
        print("Telegram error:", e)




    return "OK"


# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)










