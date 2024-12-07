import os
import sys
import logging
from PIL import Image, ImageTk
import PySimpleGUI as sg
from pillow_heif import register_heif_opener
import concurrent.futures
from io import BytesIO

# Registrar el soporte para archivos HEIF (como .heic)
register_heif_opener()

# Configurar logging
logging.basicConfig(filename='compresor_imagenes.log', level=logging.INFO,
                    format='%(asctime)s - %(nivelname)s - %(mensaje)s')

def obtener_archivos_imagen(directorio):
    extensiones_imagen = ('.jpg', '.jpeg', '.png', '.webp', '.heic', '.tiff')
    for raiz, _, archivos in os.walk(directorio):
        for archivo in archivos:
            if archivo.lower().endswith(extensiones_imagen):
                yield os.path.join(raiz, archivo)

def comprimir_imagen(ruta_entrada, ruta_salida, calidad, tamano_max=None, formato_salida=None, mantener_relacion_aspecto=True):
    try:
        with Image.open(ruta_entrada) as img:
            # Preservar metadatos EXIF
            exif = img.info.get('exif')
            
            # Redimensionar si se especifica
            if tamano_max:
                if mantener_relacion_aspecto:
                    img.thumbnail(tamano_max)
                else:
                    img = img.resize(tamano_max, Image.LANCZOS)
            
            # Determinar el formato de salida
            if formato_salida:
                formato_guardar = formato_salida
            else:
                formato_guardar = os.path.splitext(ruta_salida)[1].lower().replace('.', '')
                if formato_guardar in ('jpg', 'jpeg'):
                    formato_guardar = 'JPEG'
                elif formato_guardar == 'png':
                    formato_guardar = 'PNG'

            # Guardar la imagen comprimida
            if formato_guardar == 'PNG':
                img.save(ruta_salida, format=formato_guardar, optimize=True, exif=exif)
            else:
                img.save(ruta_salida, format=formato_guardar, quality=calidad, optimize=True, exif=exif)
            
        return os.path.getsize(ruta_entrada), os.path.getsize(ruta_salida)
    except Exception as e:
        logging.error(f"Error procesando {ruta_entrada}: {str(e)}")
        return 0, 0

def crear_vista_previa(ruta_imagen, tamano_max=(300, 300)):
    try:
        with Image.open(ruta_imagen) as img:
            img.thumbnail(tamano_max)
            bio = BytesIO()
            img.save(bio, format="PNG")
            return bio.getvalue()
    except Exception as e:
        logging.error(f"Error creando vista previa para {ruta_imagen}: {str(e)}")
        return None

def main():
    sg.theme('LightGrey1')

    diseño = [
        [sg.Text('Directorio de entrada:'), sg.Input(key='-ENTRADA-'), sg.FolderBrowse()],
        [sg.Text('Directorio de salida:'), sg.Input(key='-SALIDA-'), sg.FolderBrowse()],
        [sg.Text('Calidad (1-95):'), sg.Slider(range=(1, 95), default_value=85, orientation='h', size=(20, 15), key='-CALIDAD-')],
        [sg.Checkbox('Redimensionar', key='-REDIMENSIONAR-'), sg.Text('Ancho:'), sg.Input('1920', size=(5,1), key='-ANCHO-'), 
         sg.Text('Alto:'), sg.Input('1080', size=(5,1), key='-ALTO-')],
        [sg.Checkbox('Mantener relación de aspecto', default=True, key='-ASPECTO-')],
        [sg.Text('Formato de salida:'), sg.Combo(['Original', 'JPEG', 'PNG', 'WebP'], default_value='Original', key='-FORMATO-')],
        [sg.Button('Comprimir'), sg.Button('Cancelar')],
        [sg.Text('', size=(40, 1), key='-SALIDA-TEXTO-')],
        [sg.ProgressBar(100, orientation='h', size=(20, 20), key='-PROGRESO-')],
        [sg.Image(key='-IMAGEN-ANTES-'), sg.Image(key='-IMAGEN-DESPUES-')]
    ]

    ventana = sg.Window('Compresor de Imágenes Avanzado', diseño)

    while True:
        evento, valores = ventana.read()
        if evento == sg.WINDOW_CLOSED or evento == 'Cancelar':
            break
        if evento == 'Comprimir':
            directorio_entrada = valores['-ENTRADA-']
            directorio_salida = valores['-SALIDA-'] if valores['-SALIDA-'] else directorio_entrada
            calidad = int(valores['-CALIDAD-'])
            redimensionar = valores['-REDIMENSIONAR-']
            tamano_max = (int(valores['-ANCHO-']), int(valores['-ALTO-'])) if redimensionar else None
            mantener_relacion_aspecto = valores['-ASPECTO-']
            formato_salida = valores['-FORMATO-'] if valores['-FORMATO-'] != 'Original' else None

            if not os.path.isdir(directorio_entrada):
                sg.popup_error('El directorio de entrada no existe.')
                continue

            if not os.path.exists(directorio_salida):
                os.makedirs(directorio_salida)

            archivos_imagen = list(obtener_archivos_imagen(directorio_entrada))
            total_imagenes = len(archivos_imagen)

            if total_imagenes == 0:
                sg.popup_error('No se encontraron imágenes en el directorio especificado.')
                continue

            ventana['-SALIDA-TEXTO-'].update(f'Procesando {total_imagenes} imágenes...')
            barra_progreso = ventana['-PROGRESO-']
            
            tamano_original_total = 0
            tamano_comprimido_total = 0

            with concurrent.futures.ThreadPoolExecutor() as ejecutor:
                futuros = []
                for i, ruta_entrada in enumerate(archivos_imagen):
                    ruta_relativa = os.path.relpath(ruta_entrada, directorio_entrada)
                    ruta_salida = os.path.join(directorio_salida, ruta_relativa)
                    if formato_salida:
                        ruta_salida = os.path.splitext(ruta_salida)[0] + '.' + formato_salida.lower()
                    os.makedirs(os.path.dirname(ruta_salida), exist_ok=True)
                    futuros.append(ejecutor.submit(comprimir_imagen, ruta_entrada, ruta_salida, calidad, tamano_max, formato_salida, mantener_relacion_aspecto))

                    if i == 0:  # Vista previa primera imagen
                        vista_previa_antes = crear_vista_previa(ruta_entrada)
                        if vista_previa_antes:
                            ventana['-IMAGEN-ANTES-'].update(data=vista_previa_antes)

                for i, futuro in enumerate(concurrent.futures.as_completed(futuros)):
                    tamano_original, tamano_comprimido = futuro.result()
                    tamano_original_total += tamano_original
                    tamano_comprimido_total += tamano_comprimido
                    barra_progreso.UpdateBar(i + 1, total_imagenes)

                    if i == 0:  # Vista previa primera imagen comprimida
                        vista_previa_despues = crear_vista_previa(ruta_salida)
                        if vista_previa_despues:
                            ventana['-IMAGEN-DESPUES-'].update(data=vista_previa_despues)

            espacio_ahorrado = tamano_original_total - tamano_comprimido_total
            porcentaje_ahorrado = (espacio_ahorrado / tamano_original_total) * 100 if tamano_original_total > 0 else 0

            resultado = f"Proceso completado!\n"
            resultado += f"Tamaño original total: {tamano_original_total / (1024*1024):.2f} MB\n"
            resultado += f"Tamaño comprimido total: {tamano_comprimido_total / (1024*1024):.2f} MB\n"
            resultado += f"Espacio ahorrado: {espacio_ahorrado / (1024*1024):.2f} MB ({porcentaje_ahorrado:.2f}%)"

            ventana['-SALIDA-TEXTO-'].update(resultado)
            logging.info(resultado)

    ventana.close()

if __name__ == "__main__":
    main()
