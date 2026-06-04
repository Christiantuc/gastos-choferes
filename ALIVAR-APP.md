# Cómo evitar la pantalla lenta de Render (1 minuto de espera)

En el **plan gratis** de Render, la app se **apaga** si nadie la usa ~15 minutos.  
Por eso aparece la pantalla negra "WELCOME TO RENDER" y tarda ~1 minuto.

Hay **dos despertadores**. Usá los dos para máxima confiabilidad.

---

## Despertador 1 — GitHub (ya incluido en el proyecto)

1. Abrí: https://github.com/Christiantuc/gastos-choferes/actions
2. Si pide activar workflows → **Enable**
3. Deberías ver **Keep Render Alive** con ✅ verde cada ~5 minutos
4. Si no hay ejecuciones: clic en **Keep Render Alive** → **Run workflow** → **Run workflow**

---

## Despertador 2 — UptimeRobot (recomendado, 5 minutos)

Gratis y muy confiable. Tarda 5 minutos en configurar.

### Paso 1 — Crear cuenta

1. https://uptimerobot.com/signUp
2. Registrate con email (plan **Free**)

### Paso 2 — Crear monitor

1. Clic **Add New Monitor**
2. Completá:

| Campo | Valor |
|-------|--------|
| Monitor Type | **HTTP(s)** |
| Friendly Name | `Gastos choferes` |
| URL | `https://gastos-choferes.onrender.com/health` |
| Monitoring Interval | **5 minutes** |

3. **Create Monitor**

Listo. UptimeRobot visitará tu app cada 5 minutos y Render **no la apagará**.

### Paso 3 — (Opcional) Segundo monitor

Repetí con URL: `https://gastos-choferes.onrender.com/login`  
Así también se mantiene caliente la página de login.

---

## Probar que funciona

1. Configurá UptimeRobot (y verificá GitHub Actions en verde)
2. **No abras** la app durante 20 minutos
3. Entrá a: https://gastos-choferes.onrender.com/login
4. Debería cargar **directo** el login (sin pantalla negra de Render)

---

## Si aún tarda

- **Primer acceso del día:** puede tardar unos segundos (normal)
- **Solución 100%:** plan **Starter** en Render (~USD 7/mes) — el servidor nunca se apaga
