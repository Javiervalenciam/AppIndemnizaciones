# Fuentes locales

Esta carpeta debe contener los archivos `.woff2` de **Roboto** para que la
app cargue la tipografía sin depender de una CDN externa.

## Archivos esperados

```
Roboto-Regular.woff2   (peso 400)
Roboto-Medium.woff2    (peso 500)
Roboto-Bold.woff2      (peso 700)
```

> Mientras estos archivos no existan, la app sigue funcionando: el
> `font-display: swap` declarado en `assets/styles.css` provoca que el
> navegador caiga a `Helvetica Neue / Arial / sans-serif`.

## Cómo obtenerlos

### Opción 1 — Repositorio oficial de Google Fonts (recomendado)

Los archivos `.woff2` de Roboto están en el repositorio público
[`google/fonts`](https://github.com/google/fonts/tree/main/apache/roboto).
Descargue cada uno y renómbrelo así:

| Origen (en el repo) | Destino |
| --- | --- |
| `Roboto[wdth,wght].woff2` (variable) o `static/Roboto-Regular.ttf` convertido | `Roboto-Regular.woff2` |
| `static/Roboto-Medium.ttf` convertido | `Roboto-Medium.woff2` |
| `static/Roboto-Bold.ttf` convertido | `Roboto-Bold.woff2` |

### Opción 2 — google-webfonts-helper

Visite <https://gwfh.mranftl.com/fonts/roboto>, marque los pesos 400, 500 y
700, formato `woff2 (modern browsers)`, descargue el ZIP y copie los tres
archivos a esta carpeta con los nombres exactos indicados arriba.

### Opción 3 — Conservar fallback del sistema

No haga nada. La app usará Arial / sans-serif del sistema. Es válido para
desarrollo; para producción se recomienda colocar los `.woff2`.

## Licencia

Roboto se distribuye bajo la **Apache License 2.0**. Mantenga el archivo
`LICENSE` correspondiente si redistribuye la aplicación.
