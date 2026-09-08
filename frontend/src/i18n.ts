import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./locales/en.json";
import zh from "./locales/zh.json";

const STORAGE_KEY = "grc.lang";

void i18n.use(initReactI18next).init({
  resources: { zh: { translation: zh }, en: { translation: en } },
  lng: localStorage.getItem(STORAGE_KEY) ?? "zh",
  fallbackLng: "zh",
  interpolation: { escapeValue: false },
});

export function setLanguage(lang: "zh" | "en"): void {
  localStorage.setItem(STORAGE_KEY, lang);
  void i18n.changeLanguage(lang);
}

export default i18n;
