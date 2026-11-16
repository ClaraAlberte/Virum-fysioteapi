import os
import json
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort

app = Flask(__name__)
app.secret_key = "SKIFT-DENNE-HEMMELIGHED"

DB = "svar.db"
ADMIN_PASSWORD = "virum"

# ---------- Database ----------
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS skemaer (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        navn TEXT,
        spoergsmaal TEXT,
        print_footer TEXT,
        oprettet TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS svar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        skema_id INTEGER,
        data TEXT,
        tidspunkt TEXT
    )""")
    # Migrering: tilføj print_footer hvis den mangler (eksisterende DB)
    c.execute("PRAGMA table_info(skemaer)")
    cols = [r[1] for r in c.fetchall()]
    if "print_footer" not in cols:
        c.execute("ALTER TABLE skemaer ADD COLUMN print_footer TEXT")
    conn.commit()
    conn.close()

init_db()

DEFAULT_FOOTER = "Virum Fysioterapi · Udfyld venligst med blå eller sort kuglepen · Tak for din deltagelse"

# ---------- Hjælpere ----------
def hent_skema(skema_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, navn, spoergsmaal, print_footer FROM skemaer WHERE id=?", (skema_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "navn": row[1],
        "spoergsmaal": json.loads(row[2]),
        "print_footer": row[3] or DEFAULT_FOOTER,
    }

def hent_svar(skema_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT data FROM svar WHERE skema_id=?", (skema_id,))
    rows = c.fetchall()
    conn.close()
    return [json.loads(r[0]) for r in rows]

# ---------- Login ----------
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_panel"))
        return render_template("admin_login.html", fejl="Forkert adgangskode")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))

# ---------- Admin panel ----------
@app.route("/admin/panel")
def admin_panel():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, navn, oprettet FROM skemaer ORDER BY id DESC")
    skemaer = c.fetchall()
    conn.close()
    return render_template("admin_panel.html", skemaer=skemaer)

# ---------- Byg/rediger skema ----------
@app.route("/admin/byg", methods=["GET", "POST"])
@app.route("/admin/byg/<int:skema_id>", methods=["GET", "POST"])
def byg_skema(skema_id=None):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        navn = request.form.get("navn", "Spørgeskema")
        footer = request.form.get("print_footer", "").strip() or DEFAULT_FOOTER
        spoergsmaal = []
        i = 0
        while f"spoergsmaal_{i}" in request.form:
            tekst = request.form.get(f"spoergsmaal_{i}", "").strip()
            type_ = request.form.get(f"type_{i}", "text")
            bredde = request.form.get(f"bredde_{i}", "fuld")  # NY: Læs bredde
            valg = request.form.get(f"valg_{i}", "").strip()
            likert_min = request.form.get(f"likert_min_{i}", "1").strip() or "1"
            likert_max = request.form.get(f"likert_max_{i}", "5").strip() or "5"
            likert_tekster = request.form.get(f"likert_tekster_{i}", "").strip()

            if tekst:
                sp = {"tekst": tekst, "type": type_, "valg": [], "bredde": bredde}  # NY: Gem bredde
                if type_ == "valg":
                    sp["valg"] = [v.strip() for v in valg.split(",") if v.strip()]
                elif type_ == "likert":
                    try:
                        lo = int(likert_min); hi = int(likert_max)
                    except ValueError:
                        lo, hi = 1, 5
                    if lo > hi:
                        lo, hi = hi, lo
                    sp["likert_min"] = lo
                    sp["likert_max"] = hi
                    sp["likert_tekster"] = [
                        t.strip() for t in likert_tekster.split(",") if t.strip()
                    ]
                spoergsmaal.append(sp)
            i += 1

        conn = sqlite3.connect(DB)
        c = conn.cursor()
        if skema_id:
            c.execute("UPDATE skemaer SET navn=?, spoergsmaal=?, print_footer=? WHERE id=?",
                      (navn, json.dumps(spoergsmaal, ensure_ascii=False), footer, skema_id))
        else:
            c.execute("INSERT INTO skemaer (navn, spoergsmaal, print_footer, oprettet) VALUES (?,?,?,datetime('now'))",
                      (navn, json.dumps(spoergsmaal, ensure_ascii=False), footer))
            skema_id = c.lastrowid
        conn.commit()
        conn.close()
        return redirect(url_for("admin_panel"))

    if skema_id:
        skema = hent_skema(skema_id)
        if not skema:
            abort(404)
    else:
        skema = {"navn": "", "spoergsmaal": [], "print_footer": DEFAULT_FOOTER}
    return render_template("byg_skema.html", skema=skema, default_footer=DEFAULT_FOOTER)

# ---------- Besvar (offentligt) ----------
@app.route("/s/<int:skema_id>", methods=["GET", "POST"])
def besvar(skema_id):
    skema = hent_skema(skema_id)
    if not skema:
        abort(404)

    if request.method == "POST":
        svar = {}
        for i, sp in enumerate(skema["spoergsmaal"]):
            svar[sp["tekst"]] = request.form.get(f"s_{i}", "")
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("INSERT INTO svar (skema_id, data, tidspunkt) VALUES (?,?,datetime('now'))",
                  (skema_id, json.dumps(svar, ensure_ascii=False)))
        conn.commit()
        conn.close()
        return render_template("besvar.html", skema=skema, tak=True)

    return render_template("besvar.html", skema=skema, tak=False)

# ---------- Statistik ----------
@app.route("/admin/statistik/<int:skema_id>")
def statistik(skema_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    skema = hent_skema(skema_id)
    if not skema:
        abort(404)
    svar = hent_svar(skema_id)
    return render_template("statistik.html", skema=skema, svar=svar)

# ---------- Print ----------
@app.route("/admin/print/<int:skema_id>")
def print_skema(skema_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    skema = hent_skema(skema_id)
    if not skema:
        abort(404)
    
    # NYT: Vi tildeler numre til spørgsmålene her, så print.html ikke skal gætte.
    spoergsmaal = skema["spoergsmaal"]
    for i, sp in enumerate(spoergsmaal):
        sp["nummer"] = i + 1
        
    # NYT: Vi grupperer spørgsmålene i rækker, så 2 halv-bredde spørgsmål bliver parret
    raekker = []
    i = 0
    while i < len(spoergsmaal):
        sp = spoergsmaal[i]
        # Hvis spørgsmålet er halvt, og det næste også er halvt -> par dem
        if sp.get("bredde") == "halv" and i + 1 < len(spoergsmaal) and spoergsmaal[i+1].get("bredde") == "halv":
            raekker.append([sp, spoergsmaal[i+1]])
            i += 2
        else:
            # Ellers står det alene på en fuld række
            raekker.append([sp])
            i += 1
            
    return render_template("print.html", skema=skema, raekker=raekker)

# ---------- Forside ----------
@app.route("/")
def forside():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, navn FROM skemaer ORDER BY id DESC")
    skemaer = c.fetchall()
    conn.close()
    return render_template("forside.html", skemaer=skemaer)

# ---------- API ----------
@app.route("/api/svar/<int:skema_id>")
def api_svar(skema_id):
    if not session.get("admin"):
        abort(403)
    return jsonify(hent_svar(skema_id))

if __name__ == "__main__":
    app.run(debug=True, port=5000)