#include <Preferences.h>
#include <M5Unified.h>
#include <esp_system.h>

Preferences preferencias;

void mostrarPantalla(const char *linea1, const char *linea2 = "",
                     const char *linea3 = "") {
  M5.Display.clear(TFT_BLACK);
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.setTextSize(2);
  M5.Display.setCursor(4, 8);
  M5.Display.println(linea1);
  M5.Display.println(linea2);
  M5.Display.println(linea3);
}

String leerDato(const char *mensaje, size_t maximo) {
  while (true) {
    mostrarPantalla("Config NVS", mensaje, "Escribe en Serial");
    Serial.println(mensaje);
    while (!Serial.available()) {
      delay(10);
    }

    String valor = Serial.readStringUntil('\n');
    valor.trim();
    if (!valor.isEmpty() && valor.length() <= maximo) {
      return valor;
    }

    mostrarPantalla("Dato invalido", "Intenta otra vez");
    Serial.printf("Entrada vacia o demasiado larga (maximo %u caracteres).\n",
                  static_cast<unsigned>(maximo));
  }
}

String generarToken() {
  static const char DIGITOS_HEX[] = "0123456789abcdef";
  uint8_t bytes[24]; // 48 caracteres hexadecimales aleatorios.
  esp_fill_random(bytes, sizeof(bytes));

  String token;
  token.reserve(sizeof(bytes) * 2);
  for (uint8_t byte : bytes) {
    token += DIGITOS_HEX[byte >> 4];
    token += DIGITOS_HEX[byte & 0x0f];
  }
  return token;
}

void setup() {
  M5.begin();
  mostrarPantalla("Config baliza", "Iniciando...");
  Serial.begin(115200);
  Serial.setTimeout(60000);
  delay(1000);

  Serial.println("Configurador NVS CascoVision");
  Serial.println("Ingresa los datos en el Monitor Serial (115200 baudios).");

  if (!preferencias.begin("baliza", false)) {
    mostrarPantalla("Error NVS", "No se pudo abrir");
    Serial.println("ERROR: no se pudo abrir la memoria NVS.");
    return;
  }

  String ssidGuardado = preferencias.getString("wifi_ssid", "");
  String passwordGuardada = preferencias.getString("wifi_password", "");
  String beaconGuardado = preferencias.getString("beacon_id", "");
  String zonaGuardada = preferencias.getString("zone_id", "");
  String tokenGuardado = preferencias.getString("token", "");
  String apiGuardada = preferencias.getString("api_url", "");
  if (!ssidGuardado.isEmpty() && !passwordGuardada.isEmpty() &&
      !beaconGuardado.isEmpty() && !zonaGuardada.isEmpty() &&
      !tokenGuardado.isEmpty()) {
    if (!apiGuardada.isEmpty()) {
      String reconfigurar = leerDato("Cambiar Wi-Fi/API? SI/NO:", 3);
      reconfigurar.toLowerCase();
      if (reconfigurar != "si") {
        mostrarPantalla("Sin cambios", "Config conservada", "Token en Serial");
        Serial.println("Se conserva la configuracion NVS existente.");
        Serial.printf("beacon_id: %s\nzone_id: %s\n", beaconGuardado.c_str(),
                      zonaGuardada.c_str());
        Serial.println("BALIZA_TOKEN guardado:");
        Serial.println(tokenGuardado);
        preferencias.end();
        return;
      }

      String ssid = leerDato("Nuevo SSID Wi-Fi (max. 32):", 32);
      String password = leerDato("Nueva contrasena Wi-Fi (max. 63):", 63);
      String apiUrl = leerDato("Nueva URL API http://IP:8000:", 63);
      while (!apiUrl.startsWith("http://")) {
        Serial.println("La URL debe comenzar con http://");
        apiUrl = leerDato("Nueva URL API http://IP:8000:", 63);
      }
      while (apiUrl.endsWith("/")) apiUrl.remove(apiUrl.length() - 1);

      bool guardado = preferencias.putString("wifi_ssid", ssid) > 0;
      guardado = (preferencias.putString("wifi_password", password) > 0) && guardado;
      guardado = (preferencias.putString("api_url", apiUrl) > 0) && guardado;
      const bool verificado = guardado &&
                              preferencias.getString("wifi_ssid", "") == ssid &&
                              preferencias.getString("wifi_password", "") == password &&
                              preferencias.getString("api_url", "") == apiUrl &&
                              preferencias.getString("beacon_id", "") == beaconGuardado &&
                              preferencias.getString("zone_id", "") == zonaGuardada &&
                              preferencias.getString("token", "") == tokenGuardado;
      preferencias.end();
      mostrarPantalla(verificado ? "Red actualizada" : "Error al guardar",
                      verificado ? "Token conservado" : "Revisa Monitor");
      Serial.println(verificado
                         ? "Wi-Fi y URL API actualizados; IDs y token conservados."
                         : "ERROR: no se pudo guardar o verificar la configuracion.");
      return;
    }

    String apiUrl = leerDato("URL API http://IP:8000:", 63);
    while (!apiUrl.startsWith("http://")) {
      Serial.println("La URL debe comenzar con http://");
      apiUrl = leerDato("URL API http://IP:8000:", 63);
    }
    while (apiUrl.endsWith("/")) apiUrl.remove(apiUrl.length() - 1);
    const bool guardado = preferencias.putString("api_url", apiUrl) > 0;
    const bool verificado = guardado &&
                            preferencias.getString("api_url", "") == apiUrl;
    preferencias.end();
    mostrarPantalla(verificado ? "URL API guardada" : "Error al guardar",
                    verificado ? "Token conservado" : "Revisa Monitor");
    Serial.println(verificado ? "URL API guardada; token existente conservado."
                              : "ERROR: no se pudo guardar la URL API.");
    return;
  }

  String ssid = leerDato("SSID Wi-Fi (max. 32):", 32);
  String password = leerDato("Contrasena Wi-Fi (max. 63):", 63);
  String beaconId = leerDato("beacon_id (max. 32):", 32);
  String zoneId = leerDato("zone_id (max. 32):", 32);
  String apiUrl = leerDato("URL API http://IP:8000:", 63);
  while (!apiUrl.startsWith("http://")) {
    Serial.println("La URL debe comenzar con http://");
    apiUrl = leerDato("URL API http://IP:8000:", 63);
  }
  while (apiUrl.endsWith("/")) apiUrl.remove(apiUrl.length() - 1);
  String token = generarToken();

  bool guardado = preferencias.putString("wifi_ssid", ssid) > 0;
  guardado = (preferencias.putString("wifi_password", password) > 0) && guardado;
  guardado = (preferencias.putString("beacon_id", beaconId) > 0) && guardado;
  guardado = (preferencias.putString("zone_id", zoneId) > 0) && guardado;
  guardado = (preferencias.putString("api_url", apiUrl) > 0) && guardado;
  guardado = (preferencias.putString("token", token) > 0) && guardado;

  bool verificado = guardado &&
                    preferencias.getString("wifi_ssid", "") == ssid &&
                    preferencias.getString("wifi_password", "") == password &&
                    preferencias.getString("beacon_id", "") == beaconId &&
                    preferencias.getString("zone_id", "") == zoneId &&
                    preferencias.getString("api_url", "") == apiUrl &&
                    preferencias.getString("token", "") == token;
  preferencias.end();

  if (!verificado) {
    mostrarPantalla("Error al guardar", "Revisa Monitor", "Serial");
    Serial.println("ERROR: no se pudo guardar o verificar la configuracion.");
    return;
  }

  mostrarPantalla("Configuracion", "guardada", "Token en Serial");
  Serial.println("Configuracion guardada y verificada en NVS.");
  Serial.printf("beacon_id: %s\nzone_id: %s\n", beaconId.c_str(), zoneId.c_str());
  Serial.println("Copia este token a BALIZA_TOKEN en el equipo del agente:");
  Serial.println(token);
  Serial.println("Guarda el token de forma segura; no se mostrara otra vez.");
}

void loop() {
  delay(1000);
}
