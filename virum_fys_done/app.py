import os
import json
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort

app = Flask(__name__)
app.secret_key = "SKIFT-DENNE-HEMMELIGHED"  # vigtigt i produktion!

DB = "svar.db"
ADMIN_PASSWORD = "virum2024"  # skift til noget sikkert

# ---------- Database ----------
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS skemaer (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        navn TEXT,
        spoergsmaal TEXT,      -- JSON-liste
        oprettet TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS svar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        skema_id INTEGER,
        data TEXT,             -- JSON-dict
        tidspunkt TEXT
    )""")
    conn.commit()
    conn.close()

init_db()

# ---------- Hjælpere ----------
def hent_skema(skema_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, navn, spoergsmaal FROM skemaer WHERE id=?", (skema_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "navn": row[1], "spoergsmaal": json.loads(row[2])}

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

def kraev_admin():
    if not session.get("admin"):
        abort(redirect(url_for("admin_login")))

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
        spoergsmaal = []
        i = 0
        while f"spoergsmaal_{i}" in request.form:
            tekst = request.form.get(f"spoergsmaal_{i}", "").strip()
            type_ = request.form.get(f"type_{i}", "text")
            valg = request.form.get(f"valg_{i}", "").strip()
            if tekst:
                spoergsmaal.append({
                    "tekst": tekst,
                    "type": type_,
                    "valg": [v.strip() for v in valg.split(",") if v.strip()] if valg else []
                })
            i += 1

        conn = sqlite3.connect(DB)
        c = conn.cursor()
        if skema_id:
            c.execute("UPDATE skemaer SET navn=?, spoergsmaal=? WHERE id=?",
                      (navn, json.dumps(spoergsmaal, ensure_ascii=False), skema_id))
        else:
            c.execute("INSERT INTO skemaer (navn, spoergsmaal, oprettet) VALUES (?,?,datetime('now'))",
                      (navn, json.dumps(spoergsmaal, ensure_ascii=False)))
            skema_id = c.lastrowid
        conn.commit()
        conn.close()
        return redirect(url_for("admin_panel"))

    skema = hent_skema(skema_id) if skema_id else {"navn": "", "spoergsmaal": []}
    return render_template("byg_skema.html", skema=skema)

# ---------- Besvar (offentligt, anonymt) ----------
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

# ---------- Statistik (admin) ----------
@app.route("/admin/statistik/<int:skema_id>")
def statistik(skema_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    skema = hent_skema(skema_id)
    if not skema:
        abort(404)
    svar = hent_svar(skema_id)
    return render_template("statistik.html", skema=skema, svar=svar)

@app.route("/")
def forside():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, navn FROM skemaer ORDER BY id DESC")
    skemaer = c.fetchall()
    conn.close()
    return render_template("forside.html", skemaer=skemaer)

# ---------- API til frontend-filtrering ----------
@app.route("/api/svar/<int:skema_id>")
def api_svar(skema_id):
    if not session.get("admin"):
        abort(403)
    return jsonify(hent_svar(skema_id))

if __name__ == "__main__":
    app.run(debug=True, port=5000)