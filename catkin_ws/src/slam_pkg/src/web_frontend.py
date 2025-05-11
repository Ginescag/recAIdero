#codigo hecho por Gines Caballero Guijarro 

from flask import Flask, render_template_string, request, redirect, url_for
import subprocess
import os

app = Flask(__name__)


RECAIDERO_SCRIPT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "recAIdero.py"))
DEFAULT_MAP_PATH = os.path.abspath(os.path.join(os.path.dirname(RECAIDERO_SCRIPT_PATH), '..', 'Maps', 'finalWorld.yaml'))

last_operation_result = {
    "output": None,
    "error": None,
    "query_text": None
}

HTML_TEMPLATE = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>RecAIdero - Interfaz NLP</title>
  <style>
    body { font-family: sans-serif; margin: 20px; background-color: #f4f4f4; color: #333; }
    h1 { color: #444; }
    .container { background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); margin-bottom: 20px;}
    label { font-weight: bold; }
    input[type="text"] { width: 80%; padding: 10px; margin-top: 5px; margin-bottom: 15px; border: 1px solid #ddd; border-radius: 4px; }
    input[type="submit"], button { padding: 10px 15px; border: none; border-radius: 4px; cursor: pointer; margin-right: 10px; }
    input[type="submit"].send-command { background-color: #007bff; color: white; }
    input[type="submit"].send-command:hover { background-color: #0056b3; }
    button.cancel-pickup { background-color: #dc3545; color: white; }
    button.cancel-pickup:hover { background-color: #c82333; }
    .output-area { margin-top: 20px; }
    .status-box { border: 1px solid #ccc; padding: 10px; margin-top: 10px; background-color: #f9f9f9; border-radius: 4px;}
    pre { background-color: #eee; padding: 15px; border-radius: 4px; white-space: pre-wrap; word-wrap: break-word; max-height: 400px; overflow-y: auto;}
    .error-message { color: red; font-weight: bold; }
    .output-log { color: #333; } /* Changed from green to default for better readability of mixed logs */
  </style>
</head>
<body>
  <div class="container">
    <h1>Enviar comando al Robot RecAIdero</h1>
    <form method="post" action="{{ url_for('process_query') }}">
      <label for="query_text">Introduce tu frase de lenguaje natural:</label><br>
      <input type="text" id="query_text" name="query_text" size="50" value="{{ query_text if query_text else '' }}"><br><br>
      <input type="submit" class="send-command" value="Enviar Comando">
    </form>
    <form method="post" action="{{ url_for('cancel_and_return_home') }}" style="display: inline-block; margin-top: 10px;">
      <button type="submit" class="cancel-pickup">Cancelar Recogida y Volver a Casa</button>
    </form>
  </div>

  <div class="container output-area">
    <h2>Estado y Mensajes del Robot:</h2>
    <div class="status-box">
        {% if output_log %}
        <pre class="output-log">{{ output_log }}</pre>
        {% endif %}
        {% if error_log %}
        <pre class="error-message">{{ error_log }}</pre>
        {% endif %}
        {% if not output_log and not error_log %}
        <p>Esperando comandos...</p>
        {% endif %}
    </div>
  </div>
</body>
</html>
"""

def execute_recaidero_command(args_list):
    """
    Executes the recAIdero.py script with the given arguments.
    Returns a tuple (output_str, error_str).
    """
    output_log_lines = []
    error_log_lines = []

    if not os.path.exists(RECAIDERO_SCRIPT_PATH):
        error_log_lines.append(f"Error Crítico: No se encuentra el script recAIdero.py en {RECAIDERO_SCRIPT_PATH}")
        return "", "".join(error_log_lines)

    current_map_path = DEFAULT_MAP_PATH
    if not os.path.exists(current_map_path):
        error_log_lines.append(f"Error Crítico: El archivo de mapa '{current_map_path}' no se encuentra. ")
        error_log_lines.append(f"Asegúrate de que exista y que la variable DEFAULT_MAP_PATH en web_frontend.py sea correcta.")
        return "", "".join(error_log_lines)

    command = ["python3", RECAIDERO_SCRIPT_PATH, "--map", current_map_path] + args_list

    try:
        script_dir = os.path.dirname(RECAIDERO_SCRIPT_PATH)
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=script_dir,
            env=os.environ.copy()
        )
        stdout, stderr = process.communicate(timeout=300) 

        if stdout:
            output_log_lines.append("--- Salida del Robot ---\n")
            output_log_lines.append(stdout)
        if stderr:

            output_log_lines.append("\n--- Mensajes Adicionales (stderr) ---\n")
            output_log_lines.append(stderr)

        if process.returncode != 0:
            error_log_lines.append(f"El script recAIdero.py finalizó con errores (código: {process.returncode}).\n")

    except subprocess.TimeoutExpired:
        error_log_lines.append("La ejecución del script recAIdero.py tardó demasiado (más de 300s) y fue cancelada.\n")
        if 'process' in locals() and process:
            process.kill()
            out, err = process.communicate()
            if out: output_log_lines.append("--- Salida (antes del timeout) ---\n" + out)
            if err: output_log_lines.append("--- Errores (antes del timeout) ---\n" + err)
    except Exception as e:
        error_log_lines.append(f"Excepción al ejecutar recAIdero.py: {str(e)}\n")

    return "".join(output_log_lines), "".join(error_log_lines)


@app.route('/', methods=['GET'])
def index():
    global last_operation_result
    output_to_show = last_operation_result["output"]
    error_to_show = last_operation_result["error"]
    query_text_to_show = last_operation_result["query_text"]

    last_operation_result = {"output": None, "error": None, "query_text": None}

    return render_template_string(HTML_TEMPLATE,
                                  output_log=output_to_show,
                                  error_log=error_to_show,
                                  query_text=query_text_to_show)

@app.route('/process_query', methods=['POST'])
def process_query():
    global last_operation_result
    query_text = request.form.get('query_text')
    last_operation_result["query_text"] = query_text 

    if not query_text:
        last_operation_result["error"] = "Por favor, introduce una frase."
    else:
        output, error = execute_recaidero_command(["--query", query_text])
        last_operation_result["output"] = output
        last_operation_result["error"] = error
    
    return redirect(url_for('index'))

@app.route('/cancel_and_return_home', methods=['POST'])
def cancel_and_return_home():
    global last_operation_result
    last_operation_result["query_text"] = "Comando de cancelación y retorno a casa" 

    output, error = execute_recaidero_command(["--go_home_now"])
    last_operation_result["output"] = output
    last_operation_result["error"] = error

    return redirect(url_for('index'))

if __name__ == '__main__':
    print(f"Asegúrate de haber ejecutado 'source devel/setup.bash' en tu workspace de Catkin.")
    print(f"Asegúrate de que 'roscore' y tu stack de navegación (move_base) estén corriendo.")
    print(f"El script recAIdero.py se buscará en: {RECAIDERO_SCRIPT_PATH}")
    print(f"El mapa por defecto se buscará en: {DEFAULT_MAP_PATH}")
    print(f"Accede a la interfaz en: http://localhost:5000 o http://<tu_IP_linux>:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)