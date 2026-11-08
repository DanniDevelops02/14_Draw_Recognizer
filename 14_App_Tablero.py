import base64
import hashlib
import io
import os
import re
import tempfile
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

try:
    import openai
    from openai import OpenAI
except ImportError:  # sin la librería no se puede analizar, pero el tablero sigue funcionando
    openai = None
    OpenAI = None

st.set_page_config(
    page_title="Tablero · Daniel Flórez",
    page_icon="🎨",
    layout="centered",
    initial_sidebar_state="expanded",
)

# =====================================================================
#  CONFIGURACIÓN
# =====================================================================
# Todos estos servicios hablan el mismo "idioma" que OpenAI, así que usamos una sola librería.
# Los nombres de modelo cambian con frecuencia: si uno falla, usa «Cargar modelos».
PROVEEDORES = {
    "Google Gemini · plan gratuito": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "modelo": "gemini-flash-latest",
        "secreto": "GEMINI_API_KEY",
        "nota": "Gratis sin tarjeta, con límites por minuto y por día. En el plan gratuito, Google "
        "puede usar lo que envíes para mejorar sus productos: no dibujes nada privado.",
        "pasos": [
            "Entra a aistudio.google.com/apikey con tu cuenta de Google.",
            "Acepta los términos si te los pide.",
            "Pulsa «Create API key» y elige un proyecto (o crea uno nuevo).",
            "Copia la clave (empieza por «AIza») y pégala aquí. No la compartas ni la subas a GitHub.",
        ],
    },
    "Groq · plan gratuito": {
        "base_url": "https://api.groq.com/openai/v1",
        "modelo": "qwen/qwen3.6-27b",
        "secreto": "GROQ_API_KEY",
        "nota": "Gratis sin tarjeta y muy rápido. Solo algunos modelos aceptan imágenes (los de "
        "«visión»): si falla, pulsa «Cargar modelos» y revisa la documentación de Groq.",
        "pasos": [
            "Entra a console.groq.com/keys e inicia sesión (Google, GitHub o correo).",
            "Pulsa «Create API Key» y ponle un nombre.",
            "Copia la clave y pégala aquí.",
        ],
    },
    "OpenRouter · modelos gratuitos": {
        "base_url": "https://openrouter.ai/api/v1",
        "modelo": "openrouter/free",
        "secreto": "OPENROUTER_API_KEY",
        "nota": "Los modelos «:free» no cobran, pero tienen tope diario de solicitudes y cambian "
        "con frecuencia. Elige uno que acepte imágenes.",
        "pasos": [
            "Entra a openrouter.ai/keys e inicia sesión.",
            "Pulsa «Create Key» y copia la clave.",
            "Pégala aquí y, si falla, pulsa «Cargar modelos» para ver los gratuitos.",
        ],
    },
    "OpenAI · de pago": {
        "base_url": None,
        "modelo": "gpt-4o-mini",
        "secreto": "OPENAI_API_KEY",
        "nota": "Requiere saldo en tu cuenta de OpenAI (platform.openai.com/api-keys).",
        "pasos": [],
    },
    "Otro servicio compatible con OpenAI": {
        "base_url": "",
        "modelo": "",
        "secreto": "LLM_API_KEY",
        "nota": "Sirve para cualquier servicio con API compatible con OpenAI y modelos con visión "
        "(incluido Ollama en tu computador, que solo funciona si ejecutas la app en local).",
        "pasos": [],
    },
}

MARCO = (
    "La imagen es un boceto hecho a mano en un lienzo digital: las líneas pueden ser simples o "
    "toscas, y eso está bien. Responde siempre en español, con un tono amable y concreto."
)
TAREAS = {
    "¿Qué dibujé?": (
        "Adivina qué representa el dibujo. Da tu mejor respuesta en una frase y después "
        "2 alternativas posibles con una razón breve para cada una."
    ),
    "Describir el boceto": (
        "Describe con detalle lo que ves: qué elementos hay, cómo están colocados y qué colores se usaron."
    ),
    "Ideas para mejorarlo": (
        "Da 4 sugerencias concretas y fáciles de aplicar para mejorar o completar este dibujo."
    ),
    "Contar una historia": "Inventa una historia corta (máximo 120 palabras) inspirada en este dibujo.",
    "Pregunta personalizada": "",
}

EXCLUIR_MODELOS = (
    "embed", "whisper", "tts", "imagen", "audio", "guard", "moderation",
    "veo", "lyria", "dall-e", "transcribe", "robotics", "computer-use",
)

LADO_MAXIMO = 1024  # el dibujo se reduce a este lado máximo antes de enviarlo
ANCHO_LIENZO, ALTO_LIENZO = 800, 520
COLORES = ["#1b2f45", "#3f71a6", "#d64545", "#2f9e6f", "#f0a030", "#8a5cc2"]

# =====================================================================
#  ESTILO (paleta fría basada en #3f71a6)
# =====================================================================
PRIMARIO = "#3f71a6"
OSCURO = "#1b2f45"
CLARO = "#eaf2f9"
SUAVE = "#a9c7e3"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Playfair+Display:wght@500;600;700&display=swap');

html, body, [class*="css"], .stApp { font-family: 'Inter', sans-serif; font-size: 1.06rem; }
.stApp { background: linear-gradient(180deg, #f6fafd 0%, __CLARO__ 100%); }
header[data-testid="stHeader"] { background: transparent; }
.block-container { max-width: 860px; padding-top: 3rem; padding-bottom: 4rem; }

/* Hero */
.hero { text-align: center; padding: 1rem 0 .5rem 0; }
.hero .etiqueta {
    color: __PRIMARIO__; letter-spacing: .25em; text-transform: uppercase;
    font-size: .85rem; font-weight: 600;
}
.hero h1 {
    font-family: 'Playfair Display', serif; font-size: 3.1rem; color: __OSCURO__;
    margin: .3rem 0 .6rem 0; line-height: 1.12;
}
.hero p { color: #4d6479; font-size: 1.2rem; max-width: 620px; margin: 0 auto; }
.linea { width: 70px; height: 4px; border-radius: 4px; background: __PRIMARIO__; margin: 1.4rem auto; }
h2, h3 { font-family: 'Playfair Display', serif !important; color: __OSCURO__ !important; }
[data-testid="stHeaderActionElements"] { display: none !important; }

/* Tarjetas (contenedores con key="tarjeta_...") */
[class*="st-key-tarjeta"] {
    background: #ffffff !important;
    border: 1px solid __SUAVE__88 !important;
    border-radius: 18px !important;
    box-shadow: 0 8px 24px rgba(63, 113, 166, .08);
    padding: 1.4rem 1.5rem 1.3rem 1.5rem !important;
}
/* Texto legible dentro de las tarjetas, también si el navegador está en modo oscuro */
[class*="st-key-tarjeta"] p,
[class*="st-key-tarjeta"] label,
[class*="st-key-tarjeta"] li,
[class*="st-key-tarjeta"] [data-testid="stWidgetLabel"] * { color: __OSCURO__ !important; }
[class*="st-key-tarjeta"] [data-testid="stCaptionContainer"] * { color: #4d6479 !important; }

/* Botones e inputs */
.stButton > button, .stDownloadButton > button {
    background: __PRIMARIO__; color: white; border: 1.5px solid __PRIMARIO__;
    border-radius: 999px; padding: .65rem 1.4rem; font-weight: 600; transition: all .2s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    background: __OSCURO__; border-color: __OSCURO__; color: white; transform: translateY(-2px);
}
.stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div {
    border-radius: 12px; border: 1px solid __SUAVE__;
}
[data-testid="stAlert"] { border-radius: 14px; }

/* Respuesta de la IA */
.respuesta { color: __OSCURO__; line-height: 1.65; }

/* Sidebar */
[data-testid="stSidebar"] { background: __OSCURO__; }
[data-testid="stSidebar"] * { color: #e6f0f9 !important; }

#MainMenu, footer { visibility: hidden; }
</style>
"""


def inyectar_css() -> None:
    css = CSS
    for token, valor in {
        "__PRIMARIO__": PRIMARIO, "__OSCURO__": OSCURO, "__CLARO__": CLARO, "__SUAVE__": SUAVE,
    }.items():
        css = css.replace(token, valor)
    st.markdown(css, unsafe_allow_html=True)


# =====================================================================
#  TABLERO PARA DIBUJAR (componente propio: sin librerías externas)
# =====================================================================
TABLERO_HTML = """
<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@500;600&display=swap');
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { background: transparent; font-family: 'Inter', sans-serif; color: __OSCURO__; }
  .caja { width: 100%; padding: 4px 2px 6px 2px; }
  .barra { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 16px; margin-bottom: 12px; }
  .grupo { display: flex; align-items: center; gap: 8px; }
  .colores { display: flex; gap: 7px; }
  .color { width: 30px; height: 30px; border-radius: 50%; border: 3px solid #fff; cursor: pointer;
           box-shadow: 0 0 0 1.5px rgba(27, 47, 69, .25); transition: transform .15s ease; padding: 0; }
  .color:hover { transform: scale(1.1); }
  .color.sel { box-shadow: 0 0 0 3px __PRIMARIO__; }
  .herr { padding: .42rem .9rem; border-radius: 999px; border: 1.5px solid __PRIMARIO__; background: transparent;
          color: __PRIMARIO__; font: 600 .9rem 'Inter', sans-serif; cursor: pointer; transition: all .2s ease; }
  .herr:hover { background: __CLARO__; }
  .herr.sel { background: __PRIMARIO__; color: #fff; }
  .grosor { display: flex; align-items: center; gap: 8px; font-size: .88rem; font-weight: 500; }
  input[type=range] { width: 110px; accent-color: __PRIMARIO__; }
  .marco { border-radius: 16px; overflow: hidden; border: 2px solid __SUAVE__; background: #fff;
           box-shadow: 0 8px 22px rgba(27, 47, 69, .12); line-height: 0; position: relative; }
  canvas { width: 100%; aspect-ratio: __W__ / __H__; display: block; touch-action: none; cursor: crosshair; }
  .pista { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
           color: rgba(27, 47, 69, .35); font-size: 1.05rem; text-align: center; line-height: 1.4;
           pointer-events: none; transition: opacity .2s; padding: 1rem; }
  .pista.oculta { opacity: 0; }
  .acciones { display: flex; gap: 10px; margin-top: 12px; }
  .acciones .herr { flex: 1; padding: .6rem 0; }
  #borrar { background: __PRIMARIO__; color: #fff; }
  #borrar:hover { background: __OSCURO__; border-color: __OSCURO__; }
</style></head>
<body>
<div class="caja">
  <div class="barra">
    <div class="colores" id="colores"></div>
    <div class="grupo">
      <button class="herr sel" id="lapiz" type="button">Lápiz</button>
      <button class="herr" id="goma" type="button">Borrador</button>
    </div>
    <label class="grosor">Grosor <input id="grosor" type="range" min="2" max="40" value="6"></label>
  </div>
  <div class="marco">
    <canvas id="lienzo" width="__W__" height="__H__"></canvas>
    <div class="pista" id="pista">Dibuja aquí con el mouse o con el dedo</div>
  </div>
  <div class="acciones">
    <button class="herr" id="deshacer" type="button">Deshacer</button>
    <button class="herr" id="borrar" type="button">Borrar todo</button>
  </div>
</div>
<script>
  const W = __W__, H = __H__, PALETA = __COLORES__;
  const cv = document.getElementById("lienzo"), ctx = cv.getContext("2d");
  const pista = document.getElementById("pista");
  let color = PALETA[0], borrador = false, grosor = 6;
  let trazos = [], actual = null, contador = 0;

  function mensaje(tipo, extra) {
    window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type: tipo }, extra), "*");
  }
  const listo = () => mensaje("streamlit:componentReady", { apiVersion: 1 });
  const altura = () => mensaje("streamlit:setFrameHeight", {
    height: Math.ceil(document.querySelector(".caja").getBoundingClientRect().height) + 8
  });
  const enviar = () => {
    contador += 1;
    const img = trazos.length ? cv.toDataURL("image/png") : "";
    mensaje("streamlit:setComponentValue", { value: { n: contador, img: img }, dataType: "json" });
  };

  function dibujar() {
    ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, W, H);   // fondo blanco opaco
    ctx.lineCap = "round"; ctx.lineJoin = "round";
    for (const t of trazos) {
      const c = t.goma ? "#ffffff" : t.color;
      ctx.strokeStyle = c; ctx.fillStyle = c; ctx.lineWidth = t.ancho;
      const p = t.pts;
      if (p.length === 1) {
        ctx.beginPath(); ctx.arc(p[0][0], p[0][1], t.ancho / 2, 0, Math.PI * 2); ctx.fill();
      } else {
        ctx.beginPath(); ctx.moveTo(p[0][0], p[0][1]);
        for (let i = 1; i < p.length; i++) ctx.lineTo(p[i][0], p[i][1]);
        ctx.stroke();
      }
    }
    pista.classList.toggle("oculta", trazos.length > 0);
  }
  function pos(e) {
    const r = cv.getBoundingClientRect();
    return [(e.clientX - r.left) * W / r.width, (e.clientY - r.top) * H / r.height];
  }
  cv.addEventListener("pointerdown", (e) => {
    e.preventDefault(); cv.setPointerCapture(e.pointerId);
    actual = { color: color, goma: borrador, ancho: borrador ? grosor * 2.5 : grosor, pts: [pos(e)] };
    trazos.push(actual); dibujar();
  });
  cv.addEventListener("pointermove", (e) => {
    if (!actual) return;
    e.preventDefault(); actual.pts.push(pos(e)); dibujar();
  });
  const soltar = () => { if (actual) { actual = null; enviar(); } };
  cv.addEventListener("pointerup", soltar);
  cv.addEventListener("pointercancel", soltar);

  // Paleta y herramientas
  const cont = document.getElementById("colores");
  PALETA.forEach((c, i) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "color" + (i === 0 ? " sel" : "");
    b.style.background = c; b.setAttribute("aria-label", "Color " + (i + 1));
    b.onclick = () => {
      color = c; usarLapiz(true);
      cont.querySelectorAll(".color").forEach((x) => x.classList.remove("sel"));
      b.classList.add("sel");
    };
    cont.appendChild(b);
  });
  function usarLapiz(si) {
    borrador = !si;
    document.getElementById("lapiz").classList.toggle("sel", si);
    document.getElementById("goma").classList.toggle("sel", !si);
  }
  document.getElementById("lapiz").onclick = () => usarLapiz(true);
  document.getElementById("goma").onclick = () => usarLapiz(false);
  document.getElementById("grosor").oninput = (e) => { grosor = +e.target.value; };
  document.getElementById("deshacer").onclick = () => { trazos.pop(); dibujar(); enviar(); };
  document.getElementById("borrar").onclick = () => { trazos = []; dibujar(); enviar(); };

  dibujar(); listo(); altura();
  new ResizeObserver(altura).observe(document.body);
  window.addEventListener("message", () => altura());
</script>
</body></html>
"""


@st.cache_resource
def preparar_tablero():
    carpeta = Path(tempfile.gettempdir()) / "tablero_dibujo_componente"
    carpeta.mkdir(exist_ok=True)
    html = TABLERO_HTML
    for token, valor in {
        "__PRIMARIO__": PRIMARIO, "__OSCURO__": OSCURO, "__CLARO__": CLARO, "__SUAVE__": SUAVE,
        "__W__": str(ANCHO_LIENZO), "__H__": str(ALTO_LIENZO),
        "__COLORES__": "[" + ",".join(f'"{c}"' for c in COLORES) + "]",
    }.items():
        html = html.replace(token, valor)
    archivo = carpeta / "index.html"
    if not archivo.exists() or archivo.read_text(encoding="utf-8") != html:
        archivo.write_text(html, encoding="utf-8")
    return components.declare_component("tablero_dibujo", path=str(carpeta))


tablero = preparar_tablero()


# =====================================================================
#  LÓGICA: DIBUJO
# =====================================================================
def png_desde_valor(valor):
    """Convierte lo que manda el tablero (PNG en base64) en bytes. None si no hay dibujo."""
    if not valor or not valor.get("img"):
        return None
    texto = valor["img"]
    if "," not in texto or len(texto) > 8_000_000:
        return None
    try:
        return base64.b64decode(texto.split(",", 1)[1])
    except Exception:
        return None


def dibujo_vacio(png: bytes) -> bool:
    """True si el lienzo es todo blanco (o casi)."""
    minimo, _ = Image.open(io.BytesIO(png)).convert("L").getextrema()
    return minimo > 245


@st.cache_data(show_spinner=False, max_entries=10)
def preparar_para_ia(png: bytes) -> bytes:
    """Pone el dibujo sobre fondo blanco, lo reduce y lo devuelve como PNG limpio."""
    img = Image.open(io.BytesIO(png))
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        base = Image.new("RGB", rgba.size, (255, 255, 255))
        base.paste(rgba, mask=rgba.split()[-1])
        img = base
    else:
        img = img.convert("RGB")
    img.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
    salida = io.BytesIO()
    img.save(salida, format="PNG", optimize=True)
    return salida.getvalue()


# =====================================================================
#  LÓGICA: MODELOS CON VISIÓN
# =====================================================================
def crear_cliente(config: dict, timeout: int = 90):
    return OpenAI(
        api_key=config["clave"],
        base_url=config["base_url"] or None,
        timeout=timeout,
        max_retries=1,
    )


def listar_modelos(config: dict) -> list:
    cliente = crear_cliente(config, timeout=30)
    ids = []
    for modelo in cliente.models.list():
        nombre = modelo.id.removeprefix("models/")
        if any(x in nombre.lower() for x in EXCLUIR_MODELOS):
            continue
        ids.append(nombre)
    if config["etiqueta"].startswith("OpenRouter"):
        ids = [i for i in ids if i.endswith(":free") or i == "openrouter/free"]
    return sorted(set(ids))


def limpiar_pensamiento(texto: str) -> str:
    """Algunos modelos incluyen su razonamiento entre <think>...</think>: no se muestra."""
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.S)
    if "<think>" in texto:  # bloque todavía abierto durante la transmisión
        texto = texto.split("<think>")[0]
    return texto.strip()


def construir_mensajes(prompt: str, png: bytes) -> list:
    imagen_b64 = base64.b64encode(png).decode("utf-8")
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{imagen_b64}"}},
            ],
        }
    ]


def analizar_con_ia(config: dict, prompt: str, png: bytes, caja) -> str:
    """Envía el dibujo al modelo y va mostrando la respuesta a medida que llega."""
    cliente = crear_cliente(config)
    mensajes = construir_mensajes(prompt, png)
    texto = ""
    try:
        flujo = cliente.chat.completions.create(model=config["modelo"], messages=mensajes, stream=True)
        for trozo in flujo:
            if not trozo.choices:
                continue
            delta = trozo.choices[0].delta.content
            if delta:
                texto += delta
                caja.markdown(limpiar_pensamiento(texto) + " ▌")
    except Exception as error:
        if "stream" in str(error).lower() and not texto:  # el servicio no admite transmisión
            respuesta = cliente.chat.completions.create(model=config["modelo"], messages=mensajes)
            texto = respuesta.choices[0].message.content or ""
        else:
            raise
    final = limpiar_pensamiento(texto)
    if not final:
        raise ValueError("El modelo devolvió una respuesta vacía.")
    caja.markdown(final)
    return final


def explicar_error(error: Exception) -> str:
    if openai is not None:
        if isinstance(error, openai.AuthenticationError):
            return "La clave no es válida o no tiene permiso para este servicio."
        if isinstance(error, openai.RateLimitError):
            return (
                "Se alcanzó el límite del plan gratuito o el modelo está saturado. "
                "Espera un minuto o prueba otro modelo."
            )
        if isinstance(error, openai.NotFoundError):
            return "Ese modelo no existe en este servicio. Pulsa «Cargar modelos» y elige uno de la lista."
        if isinstance(error, openai.BadRequestError):
            return (
                "El servicio rechazó la solicitud. Lo más probable es que ese modelo no acepte "
                "imágenes: elige uno con visión."
            )
        if isinstance(error, openai.APIConnectionError):
            return "No se pudo conectar con el servicio. Revisa tu conexión a internet."
    return f"El servicio devolvió un error: {str(error)[:180]}"


def clave_guardada(nombre: str):
    """Busca la clave en los secretos de la app o en variables de entorno (nunca la escribe)."""
    try:
        valor = st.secrets.get(nombre)
        if valor:
            return str(valor)
    except Exception:
        pass
    return os.environ.get(nombre) or None


# =====================================================================
#  PÁGINA
# =====================================================================
inyectar_css()

with st.sidebar:
    st.subheader("Cómo usarlo")
    st.markdown(
        "1. Dibuja en el tablero.\n"
        "2. Pega tu clave de un servicio de IA.\n"
        "3. Elige qué quieres saber y pulsa **Analizar mi dibujo**."
    )
    st.caption("Un dibujo grande y con trazos claros se reconoce mejor.")
    st.subheader("Privacidad")
    st.markdown(
        "Al analizar, el dibujo (en PNG, sin datos del dispositivo) se envía al servicio de IA "
        "que elijas. Mientras solo dibujas, no sale de tu navegador."
    )

st.markdown(
    """
    <div class="hero">
        <div class="etiqueta">Reconocimiento de dibujos</div>
        <h1>Tablero inteligente</h1>
        <p>Haz un boceto y una inteligencia artificial te dirá qué ve en él.</p>
        <div class="linea"></div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---- 1. Tablero ----
png = None
with st.container(key="tarjeta_tablero"):
    st.subheader("1 · Dibuja tu boceto")
    valor = tablero(key="tablero", default=None)
    png = png_desde_valor(valor)
    if png is not None and dibujo_vacio(png):
        png = None
    if png is not None:
        st.download_button(
            "Descargar mi dibujo (PNG)", data=png, file_name="mi_dibujo.png", mime="image/png"
        )

# El resultado de un dibujo anterior ya no sirve cuando el dibujo cambia
huella = hashlib.md5(png).hexdigest() if png else None
if st.session_state.get("huella_dibujo") != huella:
    st.session_state["huella_dibujo"] = huella
    st.session_state.pop("resultado", None)

st.write("")

# ---- 2. Motor ----
with st.container(key="tarjeta_motor"):
    st.subheader("2 · Motor de IA")
    etiqueta = st.selectbox("Servicio", list(PROVEEDORES), label_visibility="collapsed")
    preset = PROVEEDORES[etiqueta]
    st.caption(preset["nota"])
    config = None

    if OpenAI is None:
        st.warning("Falta la librería `openai` en `requirements.txt` para poder analizar el dibujo.")
    else:
        guardada = clave_guardada(preset["secreto"])
        if guardada:
            clave = guardada
            st.success("Se usa la clave guardada en la configuración de la app.")
        else:
            clave = st.text_input(
                "Tu clave de API",
                type="password",
                key=f"clave_{etiqueta}",
                placeholder="Pega tu clave aquí",
            )
            if preset["pasos"]:
                with st.expander("¿Cómo consigo una clave gratis?"):
                    st.markdown("\n".join(f"{i}. {p}" for i, p in enumerate(preset["pasos"], 1)))

        base_url = preset["base_url"]
        if base_url == "":
            base_url = st.text_input("Dirección del servicio (base URL)", placeholder="https://.../v1")

        modelo_defecto = preset["modelo"]
        lista_clave = f"modelos_{etiqueta}"
        if st.session_state.get(lista_clave):
            lista = st.session_state[lista_clave]
            indice = lista.index(modelo_defecto) if modelo_defecto in lista else 0
            modelo = st.selectbox("Modelo (debe aceptar imágenes)", lista, index=indice)
        else:
            modelo = st.text_input(
                "Modelo (debe aceptar imágenes)", value=modelo_defecto, key=f"modelo_{etiqueta}"
            )

        config_prueba = {"etiqueta": etiqueta, "base_url": base_url, "clave": clave, "modelo": modelo}
        if clave and st.button("Cargar modelos disponibles"):
            try:
                with st.spinner("Consultando el servicio..."):
                    st.session_state[lista_clave] = listar_modelos(config_prueba)
                if not st.session_state[lista_clave]:
                    st.info("El servicio no devolvió modelos de chat.")
                st.rerun()
            except Exception as error:
                st.error(explicar_error(error))

        if clave and modelo:
            config = config_prueba
        elif not clave:
            st.info("Pega tu clave para poder analizar el dibujo.")

st.write("")

# ---- 3. Pregunta ----
with st.container(key="tarjeta_pregunta"):
    st.subheader("3 · Qué quieres saber")
    tarea = st.radio("Tarea", list(TAREAS), horizontal=True, label_visibility="collapsed")
    detalle = st.text_area(
        "Contexto o pregunta (opcional)",
        placeholder="Ej: Es un animal. ¿De qué especie podría ser?",
        height=90,
    )
    analizar = st.button("Analizar mi dibujo", type="primary", use_container_width=True)

st.write("")

# ---- 4. Resultado ----
zona = st.empty()


def mostrar_guardado(res: dict):
    st.markdown(res["texto"])
    st.caption(f"Respuesta de {res['modelo']}.")


if analizar:
    if png is None:
        st.warning("Primero dibuja algo en el tablero.")
    elif config is None:
        st.warning("Falta la clave de API. Pégala en el paso 2.")
    elif tarea == "Pregunta personalizada" and not detalle.strip():
        st.warning("Escribe tu pregunta en el cuadro de contexto.")
    else:
        with zona.container(key="tarjeta_resultado"):
            st.subheader("4 · Resultado")
            caja = st.empty()
            try:
                prompt = MARCO + "\n\n" + TAREAS[tarea]
                if detalle.strip():
                    prompt += f"\n\nContexto o pregunta del usuario: {detalle.strip()}"
                with st.spinner("Mirando tu dibujo..."):
                    texto = analizar_con_ia(config, prompt.strip(), preparar_para_ia(png), caja)
                st.session_state["resultado"] = {"texto": texto, "modelo": config["modelo"]}
                st.caption(f"Respuesta de {config['modelo']}.")
            except Exception as error:
                caja.empty()
                st.error(explicar_error(error))
elif st.session_state.get("resultado"):
    with zona.container(key="tarjeta_resultado"):
        st.subheader("4 · Resultado")
        mostrar_guardado(st.session_state["resultado"])

st.write("")
st.caption("Análisis con el servicio de IA que elijas.")
