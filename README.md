# 🤖📈 AI Trading League

Sistema automatizado que conecta IAs al mercado global (USA, Europa, Asia) para gestionar carteras ficticias de 20.000€ y comparar su rendimiento.

## Setup (15 minutos)

### 1. Crea el repositorio en GitHub
- Ve a github.com → New repository
- Nombre: `ai-trading-league`
- Visibility: **Public** (necesario para GitHub Pages)
- Sube todos estos archivos

### 2. Añade tu API key como Secret
- En tu repo: Settings → Secrets and variables → Actions → New repository secret
- Nombre: `GEMINI_API_KEY`
- Valor: tu key de Google AI Studio

### 3. Activa GitHub Pages (para la web)
- Settings → Pages → Source: `Deploy from a branch`
- Branch: `main` · Folder: `/web`
- Tu web estará en: `https://TU_USUARIO.github.io/ai-trading-league`

### 4. Edita la web con tu usuario de GitHub
- Abre `web/index.html`
- Cambia `TU_USUARIO_GITHUB` por tu usuario real de GitHub

### 5. Ejecuta manualmente el primer ciclo
- Ve a Actions → "AI Trader — Ciclo diario" → Run workflow
- Verás cómo Gemini analiza el mercado y toma decisiones

## Estructura

```
ai-trading-league/
├── trader.py                        # Script principal
├── requirements.txt
├── .github/
│   └── workflows/
│       └── daily_trade.yml          # Automatización diaria (23:00)
├── data/
│   ├── portfolios/
│   │   └── gemini.json              # Estado de la cartera
│   ├── logs/
│   │   └── YYYY-MM-DD_gemini.json   # Log diario
│   └── latest_gemini.json           # Lo que lee el frontend
└── web/
    └── index.html                   # Dashboard web
```

## Añadir más IAs

1. Copia el bloque `get_gemini_decision()` en `trader.py`
2. Adapta para la nueva API (OpenAI, Anthropic, DeepSeek...)
3. Añade el nuevo secret en GitHub Settings
4. Añade la IA en el array `IAS` de `web/index.html`

## Mercados incluidos

- 🇺🇸 S&P 500 / NASDAQ (20 valores)
- 🇪🇺 EuroStoxx (ASML, LVMH, SAP, Nestlé, AstraZeneca...)
- 🇰🇷🇯🇵 Asia: KOSPI (Samsung, SK Hynix) + Nikkei (Toyota, Sony, Nintendo...)
