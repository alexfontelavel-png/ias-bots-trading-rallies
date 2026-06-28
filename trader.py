"""
AI Trader — Script principal
Se ejecuta automáticamente cada día via GitHub Actions.
Mercados: S&P500, NASDAQ, EuroStoxx, KOSPI
"""

import yfinance as yf
import json
import re
import time
import os
from datetime import datetime
from pathlib import Path
from google import genai

# ── CONFIGURACIÓN DE MERCADOS ────────────────────────────────────

MERCADOS = {
    "USA - S&P 500 / NASDAQ": [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
        "META", "TSLA", "JPM", "JNJ", "V",
        "UNH", "XOM", "LLY", "AVGO", "MA",
        "PG", "HD", "MRK", "COST", "BRK-B"
    ],
    "Europa - EuroStoxx": [
        "ASML.AS", "MC.PA",  "SAP.DE",  "LVMH.PA", "SIE.DE",
        "NESN.SW", "ROG.SW", "NOVN.SW", "AZN.L",   "SHELL.AS"
    ],
    "Asia - KOSPI / Nikkei": [
        "005930.KS",  # Samsung
        "000660.KS",  # SK Hynix
        "035420.KS",  # NAVER
        "7203.T",     # Toyota
        "6758.T",     # Sony
        "9984.T",     # SoftBank
        "6861.T",     # Keyence
        "7974.T",     # Nintendo
    ]
}

INDICES = {
    "S&P 500":   "^GSPC",
    "NASDAQ":    "^IXIC",
    "EuroStoxx": "^STOXX50E",
    "KOSPI":     "^KS11",
    "Nikkei":    "^N225",
}

INITIAL_CASH = 20_000.0
WATCHLIST = [t for tickers in MERCADOS.values() for t in tickers]

# ── DATOS DE MERCADO ─────────────────────────────────────────────

def get_market_snapshot():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Descargando datos...")

    all_tickers = WATCHLIST + list(INDICES.values())
    data = yf.download(all_tickers, period="5d", interval="1d",
                       progress=False, auto_adjust=True)

    snapshot = {
        "fecha": datetime.now().strftime("%Y-%m-%d"),
        "hora": datetime.now().strftime("%H:%M"),
        "indices": {},
        "mercados": {}
    }

    # Índices
    for nombre, ticker in INDICES.items():
        try:
            closes = data["Close"][ticker].dropna()
            if len(closes) >= 2:
                hoy, ayer = float(closes.iloc[-1]), float(closes.iloc[-2])
                snapshot["indices"][nombre] = {
                    "valor": round(hoy, 2),
                    "cambio_pct": round((hoy - ayer) / ayer * 100, 2)
                }
        except: pass

    # Acciones por mercado
    for mercado, tickers in MERCADOS.items():
        snapshot["mercados"][mercado] = {}
        for ticker in tickers:
            try:
                closes = data["Close"][ticker].dropna()
                volumes = data["Volume"][ticker].dropna()
                if len(closes) >= 2:
                    hoy, ayer = float(closes.iloc[-1]), float(closes.iloc[-2])
                    vol = float(volumes.iloc[-1]) if len(volumes) > 0 else 0
                    snapshot["mercados"][mercado][ticker] = {
                        "precio": round(hoy, 2),
                        "cambio_pct": round((hoy - ayer) / ayer * 100, 2),
                        "volumen_M": round(vol / 1_000_000, 1),
                        "precio_ayer": round(ayer, 2)
                    }
            except: pass

    total = sum(len(v) for v in snapshot["mercados"].values())
    print(f"  ✓ {total} acciones en {len(snapshot['mercados'])} mercados · {len(snapshot['indices'])} índices")
    return snapshot


def format_market_for_prompt(snapshot):
    lines = ["=== ÍNDICES GLOBALES HOY ==="]
    for nombre, d in snapshot["indices"].items():
        s = "+" if d["cambio_pct"] > 0 else ""
        lines.append(f"  {nombre:<12}: {d['valor']:>10,.2f}  ({s}{d['cambio_pct']}%)")

    for mercado, acciones in snapshot["mercados"].items():
        lines.append(f"\n=== {mercado.upper()} ===")
        lines.append(f"  {'TICKER':<12} {'PRECIO':>10} {'CAMBIO':>8} {'VOLUMEN':>10}")
        lines.append(f"  {'-'*44}")
        sorted_acc = sorted(acciones.items(), key=lambda x: abs(x[1]["cambio_pct"]), reverse=True)
        for ticker, d in sorted_acc:
            s = "+" if d["cambio_pct"] > 0 else ""
            lines.append(f"  {ticker:<12} {d['precio']:>10.2f} {s}{d['cambio_pct']:>6.2f}% {d['volumen_M']:>7.1f}M")

    return "\n".join(lines)


# ── CARTERA ──────────────────────────────────────────────────────

class Portfolio:
    def __init__(self, ia_name, data_dir="data"):
        self.ia_name = ia_name
        Path(f"{data_dir}/portfolios").mkdir(parents=True, exist_ok=True)
        Path(f"{data_dir}/logs").mkdir(parents=True, exist_ok=True)
        self.filepath = Path(f"{data_dir}/portfolios/{ia_name}.json")
        self.logs_dir = Path(f"{data_dir}/logs")
        self.state = self._load()

    def _load(self):
        if self.filepath.exists():
            with open(self.filepath) as f:
                return json.load(f)
        return {
            "ia": self.ia_name,
            "cash": INITIAL_CASH,
            "posiciones": {},
            "historial": [],
            "valor_historico": []
        }

    def save(self):
        with open(self.filepath, "w") as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)

    def get_valor_total(self, precios):
        total = self.state["cash"]
        for ticker, pos in self.state["posiciones"].items():
            total += pos["cantidad"] * precios.get(ticker, pos["precio_medio"])
        return round(total, 2)

    def get_resumen_para_prompt(self, precios):
        valor_total = self.get_valor_total(precios)
        rent = (valor_total - INITIAL_CASH) / INITIAL_CASH * 100
        lines = [
            "=== TU CARTERA ACTUAL ===",
            f"  Valor total:   {valor_total:,.2f}€",
            f"  Rentabilidad:  {'+' if rent>=0 else ''}{rent:.2f}% vs inicio",
            f"  Cash libre:    {self.state['cash']:,.2f}€",
        ]
        if self.state["posiciones"]:
            lines.append("\n  Posiciones abiertas:")
            for ticker, pos in self.state["posiciones"].items():
                precio_actual = precios.get(ticker, pos["precio_medio"])
                valor_pos = pos["cantidad"] * precio_actual
                pnl = (precio_actual - pos["precio_medio"]) / pos["precio_medio"] * 100
                lines.append(
                    f"    {ticker:<12} {pos['cantidad']} acc × {precio_actual:.2f}"
                    f" = {valor_pos:,.0f}€   (compra: {pos['precio_medio']:.2f} | P&L: {'+' if pnl>=0 else ''}{pnl:.1f}%)"
                )
        else:
            lines.append("\n  Sin posiciones abiertas (100% cash)")
        return "\n".join(lines)

    def ejecutar_operaciones(self, operaciones, precios, fecha):
        trades = []
        for op in operaciones:
            ticker = op.get("ticker", "").upper()
            accion = op.get("accion", "mantener").lower()
            cantidad = int(op.get("cantidad", 0))
            justificacion = op.get("justificacion", "")
            if accion == "mantener" or cantidad == 0: continue
            precio = precios.get(ticker)
            if not precio:
                # Prueba sin sufijo de mercado (por si acaso)
                precio = precios.get(ticker.split(".")[0])
            if not precio:
                print(f"  ⚠ Sin precio para {ticker}")
                continue
            if accion == "comprar":
                coste = cantidad * precio
                if coste > self.state["cash"]:
                    cantidad = int(self.state["cash"] / precio)
                    coste = cantidad * precio
                if cantidad == 0:
                    print(f"  ⚠ Sin cash para {ticker}")
                    continue
                if ticker in self.state["posiciones"]:
                    pos = self.state["posiciones"][ticker]
                    total = pos["cantidad"] + cantidad
                    pm = (pos["cantidad"] * pos["precio_medio"] + coste) / total
                    self.state["posiciones"][ticker] = {"cantidad": total, "precio_medio": round(pm, 4)}
                else:
                    self.state["posiciones"][ticker] = {"cantidad": cantidad, "precio_medio": round(precio, 4)}
                self.state["cash"] -= coste
                print(f"  ✅ COMPRA {cantidad} {ticker} @ {precio:.2f} = {coste:,.0f}€")
            elif accion == "vender":
                if ticker not in self.state["posiciones"]:
                    print(f"  ⚠ No tienes {ticker}")
                    continue
                cantidad = min(cantidad, self.state["posiciones"][ticker]["cantidad"])
                ingreso = cantidad * precio
                self.state["posiciones"][ticker]["cantidad"] -= cantidad
                if self.state["posiciones"][ticker]["cantidad"] == 0:
                    del self.state["posiciones"][ticker]
                self.state["cash"] += ingreso
                print(f"  ✅ VENTA  {cantidad} {ticker} @ {precio:.2f} = {ingreso:,.0f}€")
            trades.append({
                "fecha": fecha,
                "accion": accion,
                "ticker": ticker,
                "cantidad": cantidad,
                "precio": precio,
                "justificacion": justificacion
            })
        self.state["historial"].extend(trades)
        self.save()
        return trades


# ── GEMINI TRADER ────────────────────────────────────────────────

def get_gemini_decision(market_text, portfolio_text, fecha, api_key):
    client = genai.Client(api_key=api_key)

    prompt = f"""Eres un gestor de cartera global con acceso a mercados de USA, Europa y Asia.
Hoy es {fecha}. Gestionas una cartera ficticia de 20.000€.

{portfolio_text}

{market_text}

REGLAS DE INVERSIÓN:
- No superar el 25% de la cartera total en una sola posición.
- No gastar más cash del disponible.
- Solo puedes operar con los tickers exactos que aparecen en la tabla.
- Horizonte de inversión: medio plazo (semanas a meses).
- Puedes diversificar entre mercados geográficos si lo ves conveniente.

TAREA: Analiza el mercado global de hoy y decide qué hacer.

Responde ÚNICAMENTE con este JSON (sin markdown, sin texto fuera del JSON):
{{
  "razonamiento_general": "Análisis detallado del mercado global hoy: qué está pasando en USA, Europa y Asia, qué sectores destacan, qué macro influye, y cuál es tu visión general. Mínimo 4-5 frases.",
  "operaciones": [
    {{
      "ticker": "AAPL",
      "accion": "comprar|vender|mantener",
      "cantidad": 10,
      "justificacion": "Explicación detallada y específica de por qué tomas esta decisión con este ticker concreto. Menciona valoración, momentum, contexto sectorial o macro. Mínimo 2-3 frases."
    }}
  ],
  "perspectiva": "Tu visión para los próximos 5-10 días de trading: qué catalizadores vigilas, qué riesgos ves, cómo posicionas la cartera. 3-4 frases.",
  "confianza": 75,
  "resumen_cartera": "Descripción breve de cómo queda la cartera tras las operaciones de hoy y por qué tiene sentido esta composición."
}}

Si hoy no ves oportunidades claras, devuelve operaciones vacías y explica por qué en razonamiento_general."""

    print("  Consultando a Gemini 2.5 Flash...")
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        raw = response.text.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match: raw = match.group(0)
        decision = json.loads(raw)
        print(f"  ✓ Gemini decidió ({len(decision.get('operaciones', []))} operaciones)")
        return decision
    except Exception as e:
        if "429" in str(e):
            print("  ⏳ Rate limit, esperando 20s...")
            time.sleep(20)
            return get_gemini_decision(market_text, portfolio_text, fecha, api_key)
        print(f"  ⚠ Error: {e}")
        return {"razonamiento_general": f"Error: {e}", "operaciones": [],
                "perspectiva": "", "confianza": 0, "resumen_cartera": ""}


# ── RUNNER PRINCIPAL ─────────────────────────────────────────────

def run():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY no encontrada en variables de entorno")
        return

    fecha = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"  AI TRADER GLOBAL · Gemini · {fecha}")
    print(f"{'='*60}\n")

    # 1. Mercado
    snapshot = get_market_snapshot()
    market_text = format_market_for_prompt(snapshot)
    precios = {}
    for acciones in snapshot["mercados"].values():
        for ticker, d in acciones.items():
            precios[ticker] = d["precio"]

    # 2. Cartera
    portfolio = Portfolio("gemini")
    portfolio_text = portfolio.get_resumen_para_prompt(precios)
    print(portfolio_text + "\n")

    # 3. Decisión
    decision = get_gemini_decision(market_text, portfolio_text, fecha, api_key)

    # 4. Operaciones
    print("\n--- Operaciones de hoy ---")
    trades = portfolio.ejecutar_operaciones(
        decision.get("operaciones", []), precios, fecha
    )
    if not trades:
        print("  Sin operaciones hoy")

    # 5. Guardar estado
    valor_total = portfolio.get_valor_total(precios)
    portfolio.state["valor_historico"].append({
        "fecha": fecha,
        "valor": valor_total,
        "rentabilidad_pct": round((valor_total - INITIAL_CASH) / INITIAL_CASH * 100, 2)
    })
    portfolio.save()

    # 6. Log del día (lo que leerá el frontend)
    log = {
        "fecha": fecha,
        "ia": "gemini",
        "modelo": "gemini-2.5-flash",
        "valor_cartera": valor_total,
        "rentabilidad_pct": round((valor_total - INITIAL_CASH) / INITIAL_CASH * 100, 2),
        "cash": portfolio.state["cash"],
        "posiciones": portfolio.state["posiciones"],
        "razonamiento": decision.get("razonamiento_general", ""),
        "perspectiva": decision.get("perspectiva", ""),
        "resumen_cartera": decision.get("resumen_cartera", ""),
        "confianza": decision.get("confianza", 0),
        "operaciones": trades,
        "indices": snapshot["indices"],
        "valor_historico": portfolio.state["valor_historico"]
    }

    log_path = portfolio.logs_dir / f"{fecha}_gemini.json"
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    # 7. Actualiza el archivo latest.json (el frontend siempre lee este)
    latest_path = Path("data/latest_gemini.json")
    with open(latest_path, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    # 8. Resumen consola
    rent = (valor_total - INITIAL_CASH) / INITIAL_CASH * 100
    print(f"\n{'─'*60}")
    print(f"  📊 Cartera: {valor_total:,.2f}€  ({'+' if rent>=0 else ''}{rent:.2f}%)")
    print(f"  💬 {decision.get('razonamiento_general','')[:200]}")
    print(f"  🔮 {decision.get('perspectiva','')[:150]}")
    print(f"  ✅ Guardado en {log_path}")
    print(f"{'─'*60}\n")


if __name__ == "__main__":
    run()
