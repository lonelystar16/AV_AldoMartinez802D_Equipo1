#include <M5Unified.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <ctype.h>
#include <string.h>

namespace {
constexpr uint32_t REINTENTO_WIFI_MS = 5000;
constexpr uint32_t INTERVALO_ESTADO_API_MS = 30000;
constexpr size_t MAX_CUERPO = 1024;
constexpr size_t MAX_LOG_LOCAL_BYTES = 4096;
constexpr size_t ALERTAS_RECIENTES = 8;
constexpr char VERSION_FIRMWARE[] = "1.0.0";
constexpr char ARCHIVO_LOG_LOCAL[] = "/errores_baliza.txt";

Preferences preferencias;
WebServer servidor(80);
String wifiSsid;
String wifiPassword;
String beaconId;
String zoneId;
String apiUrl;
String token;
String cuerpoAlerta;
bool servidorIniciado = false;
bool sistemaArchivosListo = false;
bool pantallaEnLinea = false;
bool pantallaSinWifi = false;
bool configuracionValida = false;
bool cuerpoAlertaGrande = false;
bool largoCuerpoInvalido = false;
size_t largoCuerpoEsperado = 0;
bool alertando = false;
bool sonidoSilenciado = false;
bool apiDisponible = false;
bool bdDisponible = false;
bool estadoServiciosConsultado = false;
String sonidoAlerta;
String idAlertaActual;
String idsRecientes[ALERTAS_RECIENTES];
size_t indiceAlertaReciente = 0;
uint32_t inicioAlerta = 0;
uint32_t duracionAlertaMs = 0;
uint32_t siguienteTono = 0;
uint8_t faseSirena = 0;
uint32_t ultimoIntentoWifi = 0;
uint32_t inicioWifi = 0;
uint32_t ultimoChequeoApi = 0;

void mostrar(const char *linea1, const char *linea2 = "",
             const char *linea3 = "") {
  M5.Display.clear(TFT_BLACK);
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.setTextSize(1);
  M5.Display.setCursor(4, 8);
  M5.Display.println(linea1);
  M5.Display.println(linea2);
  M5.Display.println(linea3);
}

bool cargarConfiguracion() {
  if (!preferencias.begin("baliza", true)) {
    return false;
  }

  wifiSsid = preferencias.getString("wifi_ssid", "");
  wifiPassword = preferencias.getString("wifi_password", "");
  beaconId = preferencias.getString("beacon_id", "");
  zoneId = preferencias.getString("zone_id", "");
  apiUrl = preferencias.getString("api_url", "");
  token = preferencias.getString("token", "");
  preferencias.end();

  while (apiUrl.endsWith("/")) apiUrl.remove(apiUrl.length() - 1);

  return !wifiSsid.isEmpty() && !wifiPassword.isEmpty() &&
         !beaconId.isEmpty() && !zoneId.isEmpty() &&
         apiUrl.startsWith("http://") && token.length() >= 32;
}

String escaparJson(const String &valor) {
  String salida;
  salida.reserve(valor.length() + 8);
  for (size_t i = 0; i < valor.length(); ++i) {
    const uint8_t c = static_cast<uint8_t>(valor[i]);
    switch (c) {
      case '"': salida += "\\\""; break;
      case '\\': salida += "\\\\"; break;
      case '\b': salida += "\\b"; break;
      case '\f': salida += "\\f"; break;
      case '\n': salida += "\\n"; break;
      case '\r': salida += "\\r"; break;
      case '\t': salida += "\\t"; break;
      default:
        if (c < 0x20) {
          char escape[7];
          snprintf(escape, sizeof(escape), "\\u%04x", c);
          salida += escape;
        } else {
          salida += static_cast<char>(c);
        }
    }
  }
  return salida;
}

void responderHealth() {
  const int bateria = M5.Power.getBatteryLevel();
  const bool cargando = M5.Power.isCharging();
  String cuerpo;
  cuerpo.reserve(256);
  cuerpo += F("{\"status\":\"");
  cuerpo += bateria < 15 ? F("low_battery") : F("ok");
  cuerpo += F("\",\"protocol\":\"1\",\"beacon_id\":\"");
  cuerpo += escaparJson(beaconId);
  cuerpo += F("\",\"zone_id\":\"");
  cuerpo += escaparJson(zoneId);
  cuerpo += F("\",\"firmware\":\"");
  cuerpo += VERSION_FIRMWARE;
  cuerpo += F("\",\"battery_pct\":");
  cuerpo += String(bateria);
  cuerpo += F(",\"charging\":");
  cuerpo += cargando ? F("true") : F("false");
  cuerpo += F(",\"uptime_s\":");
  cuerpo += String(millis() / 1000UL);
  cuerpo += F(",\"rssi_dbm\":");
  cuerpo += String(WiFi.RSSI());
  cuerpo += F(",\"alerting\":");
  cuerpo += alertando ? F("true}") : F("false}");
  servidor.send(200, "application/json; charset=utf-8", cuerpo);
}

void responderError(int codigo, const char *error, const char *campo = nullptr) {
  String cuerpo = "{\"error\":\"";
  cuerpo += error;
  cuerpo += '"';
  if (campo) {
    cuerpo += F(",\"field\":\"");
    cuerpo += campo;
    cuerpo += '"';
  }
  cuerpo += '}';
  servidor.send(codigo, "application/json; charset=utf-8", cuerpo);
}

void recibirCuerpoAlerta(WebServer &server, HTTPRaw &fragmento) {
  if (fragmento.status == RAW_START) {
    cuerpoAlerta = "";
    cuerpoAlertaGrande = false;
    largoCuerpoInvalido = false;
    largoCuerpoEsperado = 0;
    const String largo = server.header("Content-Length");
    if (largo.isEmpty()) {
      largoCuerpoInvalido = true;
    } else {
      for (size_t i = 0; i < largo.length(); ++i) {
        if (!isDigit(largo[i])) {
          largoCuerpoInvalido = true;
          break;
        }
        if (!cuerpoAlertaGrande) {
          largoCuerpoEsperado = largoCuerpoEsperado * 10 + (largo[i] - '0');
          if (largoCuerpoEsperado > MAX_CUERPO) cuerpoAlertaGrande = true;
        }
      }
      if (!cuerpoAlertaGrande && !largoCuerpoInvalido) {
        cuerpoAlerta.reserve(largoCuerpoEsperado);
      }
    }
  } else if (fragmento.status == RAW_WRITE && !cuerpoAlertaGrande &&
             !largoCuerpoInvalido) {
    if (fragmento.currentSize > MAX_CUERPO - cuerpoAlerta.length()) {
      cuerpoAlertaGrande = true;
      cuerpoAlerta = "";
      return;
    }
    for (size_t i = 0; i < fragmento.currentSize; ++i) {
      cuerpoAlerta += static_cast<char>(fragmento.buf[i]);
    }
  }
}

bool tokenValido(const String &recibido) {
  uint8_t diferencia = recibido.length() == token.length() ? 0 : 1;
  for (size_t i = 0; i < token.length(); ++i) {
    const char caracter = i < recibido.length() ? recibido[i] : '\0';
    diferencia |= static_cast<uint8_t>(caracter ^ token[i]);
  }
  return diferencia == 0;
}

bool uuidValido(const char *valor) {
  if (!valor || strlen(valor) != 36) return false;
  for (size_t i = 0; i < 36; ++i) {
    if (i == 8 || i == 13 || i == 18 || i == 23) {
      if (valor[i] != '-') return false;
    } else if (!isxdigit(static_cast<unsigned char>(valor[i]))) {
      return false;
    }
  }
  return true;
}

bool fechaConZonaValida(const char *valor) {
  if (!valor || strlen(valor) < 20 || valor[4] != '-' || valor[7] != '-' ||
      valor[10] != 'T' || valor[13] != ':' || valor[16] != ':') {
    return false;
  }
  for (size_t i = 0; i < 19; ++i) {
    if (i != 4 && i != 7 && i != 10 && i != 13 && i != 16 && !isDigit(valor[i])) {
      return false;
    }
  }
  size_t zona = 19;
  if (valor[zona] == '.') {
    ++zona;
    const size_t inicioFraccion = zona;
    while (isDigit(valor[zona])) ++zona;
    if (zona == inicioFraccion) return false;
  }
  if (valor[zona] == 'Z') return valor[zona + 1] == '\0';
  if ((valor[zona] != '+' && valor[zona] != '-') || strlen(valor + zona) != 6 ||
      valor[zona + 3] != ':' || !isDigit(valor[zona + 1]) ||
      !isDigit(valor[zona + 2]) || !isDigit(valor[zona + 4]) ||
      !isDigit(valor[zona + 5])) {
    return false;
  }
  const int horas = (valor[zona + 1] - '0') * 10 + valor[zona + 2] - '0';
  const int minutos = (valor[zona + 4] - '0') * 10 + valor[zona + 5] - '0';
  return horas <= 23 && minutos <= 59;
}

bool violacionValida(const char *valor) {
  return valor && (!strcmp(valor, "missing_helmet") ||
                   !strcmp(valor, "missing_reflective_vest"));
}

String textoEpp(const bool casco, const bool chaleco) {
  if (casco && chaleco) return "SIN CASCO Y CHALECO";
  if (casco) return "SIN CASCO";
  return "SIN CHALECO";
}

void mostrarAlerta(const String &nombreZona, const String &mensaje,
                   const String &textoViolacion) {
  M5.Display.fillScreen(TFT_RED);
  M5.Display.setTextColor(TFT_WHITE, TFT_RED);
  M5.Display.setTextSize(2);
  M5.Display.setCursor(4, 8);
  M5.Display.println(nombreZona);
  M5.Display.println(mensaje.isEmpty() ? textoViolacion : mensaje);
}

void iniciarAlerta(const String &id, const String &nombreZona,
                   const String &mensaje, const String &textoViolacion,
                   const String &sonido, uint32_t duracionS) {
  M5.Speaker.stop();
  alertando = true;
  sonidoSilenciado = false;
  idAlertaActual = id;
  sonidoAlerta = sonido;
  inicioAlerta = millis();
  duracionAlertaMs = duracionS * 1000UL;
  siguienteTono = inicioAlerta;
  faseSirena = 0;
  mostrarAlerta(nombreZona, mensaje, textoViolacion);
}

void agregarIdReciente(const String &id) {
  idsRecientes[indiceAlertaReciente] = id;
  indiceAlertaReciente = (indiceAlertaReciente + 1) % ALERTAS_RECIENTES;
}

void mostrarEnLinea();

void procesarAlerta() {
  if (!alertando) return;

  const uint32_t ahora = millis();
  if (ahora - inicioAlerta >= duracionAlertaMs) {
    M5.Speaker.stop();
    alertando = false;
    if (WiFi.status() == WL_CONNECTED) {
      mostrarEnLinea();
    } else {
      mostrar("Sin WiFi", "Reintentando...");
      pantallaEnLinea = false;
      pantallaSinWifi = true;
    }
    return;
  }

  if (!sonidoSilenciado && static_cast<int32_t>(ahora - siguienteTono) >= 0) {
    if (sonidoAlerta == "beep") {
      M5.Speaker.tone(1100, 120);
      siguienteTono = ahora + 1000;
    } else if (sonidoAlerta == "voice") {
      // shortcut: voice uses a short beep until prerecorded audio is packaged.
      M5.Speaker.tone(900, 180);
      siguienteTono = ahora + 1200;
    } else {
      M5.Speaker.tone(faseSirena++ % 2 ? 1250 : 780, 280);
      siguienteTono = ahora + 300;
    }
  }
}

void responderAlerta() {
  const String autorizacion = servidor.header("Authorization");
  if (!autorizacion.startsWith("Bearer ") ||
      !tokenValido(autorizacion.substring(7))) {
    responderError(401, "unauthorized");
    return;
  }

  if (!servidor.header("Content-Type").startsWith("application/json")) {
    responderError(400, "invalid_field", "body");
    return;
  }
  if (cuerpoAlertaGrande) {
    servidor.send(413, "text/plain", "");
    return;
  }
  if (largoCuerpoInvalido || largoCuerpoEsperado == 0 ||
      cuerpoAlerta.length() != largoCuerpoEsperado) {
    responderError(400, "invalid_field", "body");
    return;
  }

  StaticJsonDocument<2048> documento;
  if (deserializeJson(documento, cuerpoAlerta) || !documento.is<JsonObject>()) {
    responderError(400, "invalid_field", "body");
    return;
  }
  JsonObjectConst orden = documento.as<JsonObjectConst>();
  const char *id = orden["alert_id"].as<const char *>();
  const char *zona = orden["zone_id"].as<const char *>();
  const char *nombreZona = orden["zone_name"].as<const char *>();
  const char *sentAt = orden["sent_at"].as<const char *>();
  if (!uuidValido(id)) {
    responderError(400, "invalid_field", "alert_id");
    return;
  }
  if (!zona || !*zona) {
    responderError(400, "invalid_field", "zone_id");
    return;
  }
  if (!nombreZona || !*nombreZona || strlen(nombreZona) > 20) {
    responderError(400, "invalid_field", "zone_name");
    return;
  }

  JsonArrayConst violaciones = orden["violations"].as<JsonArrayConst>();
  if (violaciones.isNull() || violaciones.size() < 1 || violaciones.size() > 2) {
    responderError(400, "invalid_field", "violations");
    return;
  }
  bool casco = false;
  bool chaleco = false;
  for (JsonVariantConst v : violaciones) {
    const char *texto = v.as<const char *>();
    if (!violacionValida(texto)) {
      responderError(400, "invalid_field", "violations");
      return;
    }
    casco |= !strcmp(texto, "missing_helmet");
    chaleco |= !strcmp(texto, "missing_reflective_vest");
  }

  JsonVariantConst duracionValor = orden["duration_s"];
  if (!duracionValor.is<int>() || duracionValor.as<int>() < 1 ||
      duracionValor.as<int>() > 30) {
    responderError(400, "invalid_field", "duration_s");
    return;
  }
  if (!fechaConZonaValida(sentAt)) {
    responderError(400, "invalid_field", "sent_at");
    return;
  }

  if (orden.containsKey("sound") && !orden["sound"].is<const char *>()) {
    responderError(400, "invalid_field", "sound");
    return;
  }
  const char *sonido = orden["sound"] | "siren";
  if (strcmp(sonido, "siren") && strcmp(sonido, "voice") && strcmp(sonido, "beep")) {
    responderError(400, "invalid_field", "sound");
    return;
  }
  if (orden.containsKey("message") && !orden["message"].is<const char *>()) {
    responderError(400, "invalid_field", "message");
    return;
  }
  const char *mensaje = orden["message"] | "";
  if (strlen(mensaje) > 40) {
    responderError(400, "invalid_field", "message");
    return;
  }

  if (strcmp(zona, zoneId.c_str())) {
    String respuesta = "{\"error\":\"wrong_zone\",\"zone_id\":\"";
    respuesta += escaparJson(zoneId);
    respuesta += "\"}";
    servidor.send(409, "application/json; charset=utf-8", respuesta);
    return;
  }

  for (const String &reciente : idsRecientes) {
    if (reciente == id) {
      String respuesta = "{\"status\":\"alerting\",\"alert_id\":\"";
      respuesta += escaparJson(id);
      respuesta += "\",\"duplicate\":true}";
      servidor.send(200, "application/json; charset=utf-8", respuesta);
      return;
    }
  }

  agregarIdReciente(id);
  iniciarAlerta(id, nombreZona, mensaje, textoEpp(casco, chaleco), sonido,
                duracionValor.as<uint32_t>());
  procesarAlerta();

  String respuesta = "{\"status\":\"alerting\",\"alert_id\":\"";
  respuesta += escaparJson(id);
  respuesta += "\",\"duplicate\":false}";
  servidor.send(200, "application/json; charset=utf-8", respuesta);
}

class ManejadorAlerta : public RequestHandler {
 public:
  bool canHandle(WebServer &, HTTPMethod metodo, const String &uri) override {
    return metodo == HTTP_POST && uri == "/alert";
  }

  bool canRaw(WebServer &server, const String &uri) override {
    return server.method() == HTTP_POST && uri == "/alert";
  }

  bool canUpload(WebServer &, const String &) override { return false; }

  void raw(WebServer &server, const String &, HTTPRaw &fragmento) override {
    recibirCuerpoAlerta(server, fragmento);
  }

  bool handle(WebServer &, HTTPMethod metodo, const String &uri) override {
    if (!canHandle(servidor, metodo, uri)) return false;
    responderAlerta();
    return true;
  }
};

ManejadorAlerta manejadorAlerta;

void mostrarEnLinea() {
  M5.Display.clear(TFT_BLACK);
  M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
  M5.Display.setTextSize(1);
  M5.Display.setCursor(4, 8);
  M5.Display.println("Baliza en linea");
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.printf("Zona: %s\n", zoneId.c_str());
  M5.Display.printf("IP: %s\n", WiFi.localIP().toString().c_str());
  M5.Display.printf("Bateria: %d%%\n", M5.Power.getBatteryLevel());
  M5.Display.printf("RSSI: %d dBm\n", WiFi.RSSI());
  M5.Display.printf("API: %s\n", !estadoServiciosConsultado ? "consultando" :
                    apiDisponible ? "OK" : "ERROR");
  M5.Display.printf("BD: %s\n", !estadoServiciosConsultado ? "consultando" :
                    !apiDisponible ? "sin dato" : bdDisponible ? "OK" : "ERROR");
}

void guardarLogLocal(const String &mensaje) {
  Serial.println(mensaje);
  if (!sistemaArchivosListo) return;

  File archivo = LittleFS.open(ARCHIVO_LOG_LOCAL, "a");
  if (!archivo) {
    Serial.println("ERROR: no se pudo abrir el archivo local de logs.");
    return;
  }
  const String linea = String(millis() / 1000UL) + "s " + mensaje;
  // shortcut: el log local se limita a 4 KB; amplialo si se esperan cortes largos de API.
  if (archivo.size() + linea.length() + 1 <= MAX_LOG_LOCAL_BYTES) {
    archivo.println(linea);
  } else {
    Serial.println("Log local lleno; conserva los registros pendientes anteriores.");
  }
  archivo.close();
}

void enviarLogsPendientes() {
  if (!sistemaArchivosListo || !apiDisponible ||
      !LittleFS.exists(ARCHIVO_LOG_LOCAL)) return;

  File archivo = LittleFS.open(ARCHIVO_LOG_LOCAL, "r");
  if (!archivo) return;
  const String logs = archivo.readString();
  archivo.close();
  if (logs.isEmpty()) {
    LittleFS.remove(ARCHIVO_LOG_LOCAL);
    return;
  }

  String cuerpo = "{\"message\":\"" + escaparJson(logs) + "\"}";
  WiFiClient cliente;
  HTTPClient http;
  http.setTimeout(2000);
  const String ruta = apiUrl + "/edge/beacons/" + beaconId + "/logs";
  if (!http.begin(cliente, ruta)) return;
  http.addHeader("Authorization", "Bearer " + token);
  http.addHeader("Content-Type", "application/json");
  const int codigo = http.POST(cuerpo);
  http.end();

  if (codigo == HTTP_CODE_CREATED || codigo == HTTP_CODE_OK) {
    LittleFS.remove(ARCHIVO_LOG_LOCAL);
    Serial.println("Logs enviados a la API.");
  } else {
    Serial.printf("Logs pendientes: API respondio HTTP %d.\n", codigo);
  }
}

void consultarEstadoServicios() {
  WiFiClient cliente;
  HTTPClient http;
  http.setTimeout(2000);
  const String ruta = apiUrl + "/edge/beacons/" + beaconId + "/health";
  const bool iniciado = http.begin(cliente, ruta);
  int codigo = -1;
  String error;
  if (!iniciado) {
    error = "No se pudo iniciar la consulta de estado de la API.";
  } else {
    http.addHeader("Authorization", "Bearer " + token);
    codigo = http.GET();
  }
  bool apiNueva = false;
  bool bdNueva = false;
  if (codigo == HTTP_CODE_OK) {
    StaticJsonDocument<256> estado;
    if (!deserializeJson(estado, http.getString()) && estado["api"] == "ok") {
      apiNueva = true;
      bdNueva = estado["database"] == "ok";
      if (!bdNueva) error = "API disponible; PostgreSQL no responde.";
    } else {
      error = "La API devolvio un estado invalido.";
    }
  } else if (iniciado) {
    error = "Error al consultar la API; HTTP " + String(codigo) + ".";
  }
  if (iniciado) http.end();

  const bool cambio = !estadoServiciosConsultado ||
                      apiNueva != apiDisponible || bdNueva != bdDisponible;
  const bool recuperado = estadoServiciosConsultado && apiNueva && bdNueva &&
                          (!apiDisponible || !bdDisponible);
  apiDisponible = apiNueva;
  bdDisponible = bdNueva;
  estadoServiciosConsultado = true;
  if (cambio && !error.isEmpty()) guardarLogLocal(error);
  if (recuperado) guardarLogLocal("API y PostgreSQL recuperados.");
  if (apiDisponible) enviarLogsPendientes();
  if (!alertando && pantallaEnLinea) mostrarEnLinea();
}
}  // namespace

void setup() {
  M5.begin();
  M5.Speaker.setVolume(160);
  Serial.begin(115200);
  sistemaArchivosListo = LittleFS.begin(false);
  if (!sistemaArchivosListo) {
    Serial.println("ERROR: no se pudo montar LittleFS; logs solo por Serial.");
  }
  mostrar("CascoVision", "Cargando configuracion...");

  if (!cargarConfiguracion()) {
    mostrar("Falta configuracion", "Vuelve a cargar", "configurador_nvs");
    Serial.println("Falta configuracion NVS completa; carga configurador_nvs.");
    return;
  }
  configuracionValida = true;

  mostrar("Conectando WiFi", "Espera...");
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(false);
  WiFi.begin(wifiSsid.c_str(), wifiPassword.c_str());
  ultimoIntentoWifi = millis();
  inicioWifi = ultimoIntentoWifi;

  const char *cabeceras[] = {"Authorization", "Content-Type", "Content-Length"};
  servidor.collectHeaders(cabeceras, 3);
  servidor.on("/health", HTTP_GET, responderHealth);
  servidor.addHandler(&manejadorAlerta);
  servidor.onNotFound([]() {
    servidor.send(404, "application/json", "{\"error\":\"not_found\"}");
  });
}

void loop() {
  M5.update();
  if (alertando && M5.BtnA.wasPressed()) {
    sonidoSilenciado = true;
    M5.Speaker.stop();
  }
  procesarAlerta();

  if (!configuracionValida) {
    delay(100);
    return;
  }

  if (WiFi.status() == WL_CONNECTED) {
    if (!servidorIniciado) {
      servidor.begin();
      servidorIniciado = true;
      Serial.printf("Baliza lista en http://%s/health\n",
                    WiFi.localIP().toString().c_str());
    }
    if (!pantallaEnLinea) {
      mostrarEnLinea();
      pantallaEnLinea = true;
      pantallaSinWifi = false;
    }
    if (!estadoServiciosConsultado ||
        millis() - ultimoChequeoApi >= INTERVALO_ESTADO_API_MS) {
      ultimoChequeoApi = millis();
      consultarEstadoServicios();
    }
    servidor.handleClient();
    procesarAlerta();
    return;
  }

  if (!alertando && (pantallaEnLinea ||
      (!pantallaSinWifi && millis() - inicioWifi >= 15000))) {
    mostrar("Sin WiFi", "Reintentando...");
    pantallaEnLinea = false;
    pantallaSinWifi = true;
  }
  if (millis() - ultimoIntentoWifi >= REINTENTO_WIFI_MS) {
    WiFi.begin(wifiSsid.c_str(), wifiPassword.c_str());
    ultimoIntentoWifi = millis();
  }
  delay(10);
}
