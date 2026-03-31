import streamlit as st
import pandas as pd
import numpy as np
import unicodedata
from geopy.geocoders import Nominatim
import requests
import time
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Derivaciones ART", page_icon="🚑", layout="centered")

def limpiar_texto(texto):
    texto = str(texto)
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')

def calcular_distancia_linea_recta(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2.0)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2.0)**2
    c = 2 * np.arcsin(np.sqrt(a))
    return 6371 * c 

# AHORA TAMBIÉN NOS TRAEMOS EL DIBUJO DE LA RUTA (GEOJSON)
def obtener_ruta_y_distancia(lat_origen, lon_origen, lat_destino, lon_destino):
    try:
        # Le agregamos overview=full y geometries=geojson para que nos mande el trazado
        url = f"http://router.project-osrm.org/route/v1/driving/{lon_origen},{lat_origen};{lon_destino},{lat_destino}?overview=full&geometries=geojson"
        respuesta = requests.get(url, timeout=5)
        data = respuesta.json()
        
        if data.get('code') == 'Ok':
            distancia_km = data['routes'][0]['distance'] / 1000
            geometria = data['routes'][0]['geometry'] # Acá viene el dibujo de la calle
            return distancia_km, geometria
        else:
            return None, None
    except:
        return None, None

@st.cache_data 
def cargar_datos():
    # Ahora lee los archivos directamente en la carpeta donde está el programa
    df_prestadores = pd.read_csv('DIM_Prestadores.csv')
    df_especialidades = pd.read_csv('DIM_Especialidades.csv')
    df_fact_esp = pd.read_csv('FACT_Prestador_Especialidad.csv')

    df_prestadores['latitud'] = pd.to_numeric(df_prestadores['latitud'], errors='coerce')
    df_prestadores['longitud'] = pd.to_numeric(df_prestadores['longitud'], errors='coerce')
    df_prestadores = df_prestadores.dropna(subset=['latitud', 'longitud'])

    df_modelo = df_prestadores.merge(df_fact_esp, on='id_prestador').merge(df_especialidades, on='id_especialidad')
    df_modelo['especialidad_limpia'] = df_modelo['especialidad_nombre'].apply(limpiar_texto)
    return df_modelo

df_modelo = cargar_datos()

# --- ACÁ EMPIEZA LA INTERFAZ VISUAL ---
st.title("🚑 Buscador Inteligente de ART")
st.markdown("Ingresá los datos del trabajador para encontrar los prestadores más cercanos.")

# Agregamos una barra lateral para las configuraciones de plata
with st.sidebar:
    st.header("⚙️ Configuración de Viáticos")
    precio_km = st.number_input("Costo del KM en Remis ($):", min_value=0, value=850, step=50, help="Ingresá cuánto paga la ART por kilómetro.")
    st.info("💡 Este valor se usará para calcular el costo de traslado en las opciones de Remis.")

direccion = st.text_input("📍 Dirección del domicilio del trabajador (Ej: Carlos Pellegrini 1023, CABA, Argentina):")

lista_especialidades = df_modelo['especialidad_nombre'].unique()
especialidad = st.selectbox("🩺 Especialidad requerida:", sorted(lista_especialidades))

tipo_red = st.radio(
    "🏢 Seleccioná la Red de Atención:",
    ["Ambas", "Red Principal", "Red de Emergencia"],
    horizontal=True
)

if st.button("Buscar Clínicas Cercanas"):
    if direccion:
        with st.spinner('Buscando señal satelital y calculando rutas de calle...'):
           geolocator = Nominatim(user_agent="buscador_art_francoramirofusi@gmail.com")
           location = geolocator.geocode(direccion, timeout=10)
            
        if location:
                lat_accidente = location.latitude
                lon_accidente = location.longitude
                
                especialidad_busqueda = limpiar_texto(especialidad)
                mascara_esp = df_modelo['especialidad_limpia'].str.contains(especialidad_busqueda, case=False, na=False, regex=False)
                df_filtrado = df_modelo[mascara_esp].copy()
                
                if tipo_red != "Ambas":
                    df_filtrado = df_filtrado[df_filtrado['red_tipo'] == tipo_red]
                
                if not df_filtrado.empty:
                    df_filtrado['dist_recta_km'] = calcular_distancia_linea_recta(lat_accidente, lon_accidente, df_filtrado['latitud'], df_filtrado['longitud'])
                    top_6 = df_filtrado.drop_duplicates(subset=['id_prestador']).sort_values('dist_recta_km').head(6).copy()
                    
                    distancias_reales = []
                    geometrias = []
                    
                    for index, row in top_6.iterrows():
                        dist_real, geo = obtener_ruta_y_distancia(lat_accidente, lon_accidente, row['latitud'], row['longitud'])
                        if dist_real is None:
                            dist_real = row['dist_recta_km'] * 1.3 
                            geo = None
                        distancias_reales.append(dist_real)
                        geometrias.append(geo)
                        time.sleep(0.1) 
                        
                    top_6['distancia_km_ruta'] = distancias_reales
                    top_6['geometria_ruta'] = geometrias
                    
                    top_3 = top_6.sort_values('distancia_km_ruta').head(3)
                    
                    st.success("¡Rutas calculadas con éxito!")
                    st.subheader(f"Las 3 mejores opciones para {especialidad}:")
                    
                    colores_podio = ['blue', 'green', 'orange']
                    
                    for i, (index, row) in enumerate(top_3.iterrows()):
                        color_red = "🟢" if row['red_tipo'] == "Red Principal" else "🟡"
                        color_icono = colores_podio[i]
                        
                        # Calculamos la plata
                        costo_viaje = row['distancia_km_ruta'] * precio_km
                        
                        # Armamos los links oficiales de Google Maps para que ruteen automático
                        link_bondi = f"https://www.google.com/maps/dir/?api=1&origin={lat_accidente},{lon_accidente}&destination={row['latitud']},{row['longitud']}&travelmode=transit"
                        link_auto = f"https://www.google.com/maps/dir/?api=1&origin={lat_accidente},{lon_accidente}&destination={row['latitud']},{row['longitud']}&travelmode=driving"
                        
                        # Tarjeta de la clínica con solo las 2 opciones de traslado
                        st.info(f"🏥 **Opción {i+1}: {row['establecimiento_nombre']}** (Color Mapa: {color_icono.upper()})\n\n"
                                f"🏢 **Tipo:** {color_red} {row['red_tipo']} | 📍 {row['domicilio']}, {row['localidad_nombre']}\n\n"
                                f"🚗 **Distancia:** {row['distancia_km_ruta']:.2f} km\n\n"
                                f"**Opciones de Traslado:**\n\n"
                                f"1️⃣ [🚌 Ver ruta en colectivo / tren]({link_bondi})\n\n"
                                f"2️⃣ [🚕 Remis]({link_auto}) *(Costo est. un tramo: **${costo_viaje:,.2f}**)*")
                    
                    # --- MAPA INTERACTIVO (Igual que antes, con el truco del parpadeo) ---
                    st.markdown("### 🗺️ Mapa de Rutas de Evacuación")
                    m = folium.Map(location=[lat_accidente, lon_accidente], zoom_start=14)
                    folium.Marker([lat_accidente, lon_accidente], popup="Accidente", icon=folium.Icon(color="red", icon="info-sign")).add_to(m)
                    limites = [[lat_accidente, lon_accidente]]

                    for i, (index, row) in enumerate(top_3.iterrows()):
                        lat_clinica = row['latitud']
                        lon_clinica = row['longitud']
                        limites.append([lat_clinica, lon_clinica])
                        color_ruta = colores_podio[i]
                        
                        folium.Marker([lat_clinica, lon_clinica], popup=row['establecimiento_nombre'], icon=folium.Icon(color=color_ruta, icon="plus")).add_to(m)
                        if row['geometria_ruta']:
                            coordenadas_ruta = [[p[1], p[0]] for p in row['geometria_ruta']['coordinates']]
                            folium.PolyLine(coordenadas_ruta, color=color_ruta, weight=5, opacity=0.8).add_to(m)

                    m.fit_bounds(limites)
                    st_folium(m, width=700, height=500, returned_objects=[])
                    
                else:
                    st.error(f"No se encontraron clínicas en la {tipo_red} para esa especialidad en esta zona.")
            else:
                st.error("No pude encontrar la dirección. Intentá agregar la localidad, provincia y 'Argentina'.")
    else:
        st.warning("Por favor, ingresá una dirección antes de buscar.")
