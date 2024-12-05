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
logging.basicConfig(filename='image_compressor.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def get_image_files(directory):
    image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.heic', '.tiff')
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(image_extensions):
                yield os.path.join(root, file)

def compress_image(input_path, output_path, quality, max_size=None, output_format=None, keep_aspect_ratio=True):
    try:
        with Image.open(input_path) as img:
            # Preservar metadatos EXIF
            exif = img.info.get('exif')
            
            # Redimensionar si se especifica
            if max_size:
                if keep_aspect_ratio:
                    img.thumbnail(max_size)
                else:
                    img = img.resize(max_size, Image.LANCZOS)
            
            # Determinar el formato de salida
            if output_format:
                save_format = output_format
            else:
                save_format = os.path.splitext(output_path)[1].lower().replace('.', '')
                if save_format in ('jpg', 'jpeg'):
                    save_format = 'JPEG'
                elif save_format == 'png':
                    save_format = 'PNG'

            # Guardar la imagen comprimida
            if save_format == 'PNG':
                img.save(output_path, format=save_format, optimize=True, exif=exif)
            else:
                img.save(output_path, format=save_format, quality=quality, optimize=True, exif=exif)
            
        return os.path.getsize(input_path), os.path.getsize(output_path)
    except Exception as e:
        logging.error(f"Error procesando {input_path}: {str(e)}")
        return 0, 0

def create_preview(image_path, max_size=(300, 300)):
    try:
        with Image.open(image_path) as img:
            img.thumbnail(max_size)
            bio = BytesIO()
            img.save(bio, format="PNG")
            return bio.getvalue()
    except Exception as e:
        logging.error(f"Error creando vista previa para {image_path}: {str(e)}")
        return None

def main():
    sg.theme('LightGrey1')

    layout = [
        [sg.Text('Directorio de entrada:'), sg.Input(key='-IN-'), sg.FolderBrowse()],
        [sg.Text('Directorio de salida:'), sg.Input(key='-OUT-'), sg.FolderBrowse()],
        [sg.Text('Calidad (1-95):'), sg.Slider(range=(1, 95), default_value=85, orientation='h', size=(20, 15), key='-QUALITY-')],
        [sg.Checkbox('Redimensionar', key='-RESIZE-'), sg.Text('Ancho:'), sg.Input('1920', size=(5,1), key='-WIDTH-'), 
         sg.Text('Alto:'), sg.Input('1080', size=(5,1), key='-HEIGHT-')],
        [sg.Checkbox('Mantener relación de aspecto', default=True, key='-ASPECT-')],
        [sg.Text('Formato de salida:'), sg.Combo(['Original', 'JPEG', 'PNG', 'WebP'], default_value='Original', key='-FORMAT-')],
        [sg.Button('Comprimir'), sg.Button('Cancelar')],
        [sg.Text('', size=(40, 1), key='-OUTPUT-')],
        [sg.ProgressBar(100, orientation='h', size=(20, 20), key='-PROGRESS-')],
        [sg.Image(key='-IMAGE-BEFORE-'), sg.Image(key='-IMAGE-AFTER-')]
    ]

    window = sg.Window('Compresor de Imágenes Avanzado', layout)

    while True:
        event, values = window.read()
        if event == sg.WINDOW_CLOSED or event == 'Cancelar':
            break
        if event == 'Comprimir':
            input_dir = values['-IN-']
            output_dir = values['-OUT-'] if values['-OUT-'] else input_dir
            quality = int(values['-QUALITY-'])
            resize = values['-RESIZE-']
            max_size = (int(values['-WIDTH-']), int(values['-HEIGHT-'])) if resize else None
            keep_aspect_ratio = values['-ASPECT-']
            output_format = values['-FORMAT-'] if values['-FORMAT-'] != 'Original' else None

            if not os.path.isdir(input_dir):
                sg.popup_error('El directorio de entrada no existe.')
                continue

            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            image_files = list(get_image_files(input_dir))
            total_images = len(image_files)

            if total_images == 0:
                sg.popup_error('No se encontraron imágenes en el directorio especificado.')
                continue

            window['-OUTPUT-'].update(f'Procesando {total_images} imágenes...')
            progress_bar = window['-PROGRESS-']
            
            total_original_size = 0
            total_compressed_size = 0

            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = []
                for i, input_path in enumerate(image_files):
                    relative_path = os.path.relpath(input_path, input_dir)
                    output_path = os.path.join(output_dir, relative_path)
                    if output_format:
                        output_path = os.path.splitext(output_path)[0] + '.' + output_format.lower()
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    futures.append(executor.submit(compress_image, input_path, output_path, quality, max_size, output_format, keep_aspect_ratio))

                    if i == 0:  # Preview first image
                        before_preview = create_preview(input_path)
                        if before_preview:
                            window['-IMAGE-BEFORE-'].update(data=before_preview)

                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    original_size, compressed_size = future.result()
                    total_original_size += original_size
                    total_compressed_size += compressed_size
                    progress_bar.UpdateBar(i + 1, total_images)

                    if i == 0:  # Preview first compressed image
                        after_preview = create_preview(output_path)
                        if after_preview:
                            window['-IMAGE-AFTER-'].update(data=after_preview)

            space_saved = total_original_size - total_compressed_size
            space_saved_percent = (space_saved / total_original_size) * 100 if total_original_size > 0 else 0

            result = f"Proceso completado!\n"
            result += f"Tamaño original total: {total_original_size / (1024*1024):.2f} MB\n"
            result += f"Tamaño comprimido total: {total_compressed_size / (1024*1024):.2f} MB\n"
            result += f"Espacio ahorrado: {space_saved / (1024*1024):.2f} MB ({space_saved_percent:.2f}%)"

            window['-OUTPUT-'].update(result)
            logging.info(result)

    window.close()

if __name__ == "__main__":
    main()