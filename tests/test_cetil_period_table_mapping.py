from __future__ import annotations

from app_indemnizaciones.services.cetil_extractor import CetilExtractor
from app_indemnizaciones.services.cetil_models import IssueSeverity

_PAGE_TEXT = "CERTIFICACIÓN ELECTRÓNICA DE TIEMPOS LABORADOS\nCETIL"


def _table(header: list[str], *rows: list[str]) -> list[list[str | None]]:
    return [
        ["PERIODOS CERTIFICADOS", *([None] * (len(header) - 1))],
        header,
        *rows,
    ]


def test_periodos_mapeados_por_nombre_de_columna_no_por_indice():
    header = [
        "Entidad Responsable",
        "Cargo",
        "Desde (DD-MM-AAAA)",
        "Hasta (DD-MM-AAAA)",
        "Total No. Días Interrupción",
        "Tipo de Vinculación",
        "Tipo de Empleado",
    ]
    tabla = _table(
        header,
        [
            "MUNICIPIO DE PRUEBA",
            "Secretario (a)",
            "30-12-1984",
            "31-12-1985",
            "3",
            "LABORAL",
            "PÚBLICO",
        ],
    )

    result = CetilExtractor().extract_from_pages(
        {1: _PAGE_TEXT},
        tables_by_page={1: [tabla]},
    )

    assert len(result.periodos_certificados) == 1
    periodo = result.periodos_certificados[0]
    assert periodo.fecha_desde.isoformat() == "1984-12-30"
    assert periodo.fecha_hasta.isoformat() == "1985-12-31"
    assert periodo.cargo == "Secretario (a)"
    assert periodo.entidad_responsable == "MUNICIPIO DE PRUEBA"
    assert periodo.tipo_vinculacion == "LABORAL"
    assert periodo.tipo_empleado == "PÚBLICO"
    assert periodo.dias_interrupcion == 3
    assert periodo.total_no_dias == 3


def test_tabla_de_periodos_con_tres_filas_de_encabezado():
    tabla = [
        ["PERIODOS CERTIFICADOS", None, None, None],
        ["Certificación de tiempos laborados", None, None, None],
        ["Desde (DD-MM-AAAA)", "Hasta (DD-MM-AAAA)", "Cargo", "Entidad Responsable"],
        ["01-03-1979", "29-12-1984", "Ayudante", "MUNICIPIO DE PRUEBA"],
    ]

    result = CetilExtractor().extract_from_pages(
        {1: _PAGE_TEXT},
        tables_by_page={1: [tabla]},
    )

    assert len(result.periodos_certificados) == 1
    assert result.periodos_certificados[0].cargo == "Ayudante"


def test_tabla_partida_entre_paginas_se_une():
    header = ["Desde (DD-MM-AAAA)", "Hasta (DD-MM-AAAA)", "Cargo", "Entidad Responsable"]
    tabla_pagina_1 = _table(
        header,
        ["01-03-1979", "29-12-1984", "Ayudante", "MUNICIPIO DE PRUEBA"],
    )
    tabla_pagina_2 = _table(
        header,
        ["30-12-1984", "31-12-1985", "Secretario (a)", "MUNICIPIO DE PRUEBA"],
    )

    result = CetilExtractor().extract_from_pages(
        {1: _PAGE_TEXT, 2: _PAGE_TEXT},
        tables_by_page={1: [tabla_pagina_1], 2: [tabla_pagina_2]},
    )

    assert len(result.periodos_certificados) == 2
    assert [periodo.fuente_pagina for periodo in result.periodos_certificados] == [1, 2]


def test_pagina_con_tabla_y_pagina_solo_texto_se_combinan():
    header = ["Desde (DD-MM-AAAA)", "Hasta (DD-MM-AAAA)", "Cargo", "Entidad Responsable"]
    tabla = _table(
        header,
        ["01-03-1979", "31-12-1983", "Ayudante", "MUNICIPIO UNO"],
    )
    pagina_texto = """
PERIODOS CERTIFICADOS
01-01-1984 31-12-1985 LABORAL PÚBLICO Secretario ENTIDAD RESPONSABLE: MUNICIPIO DOS 0
"""

    result = CetilExtractor().extract_from_pages(
        {1: _PAGE_TEXT, 2: pagina_texto},
        tables_by_page={1: [tabla]},
    )

    assert len(result.periodos_certificados) == 2
    assert result.periodos_certificados[0].fuente_pagina == 1
    assert result.periodos_certificados[1].fuente_pagina == 2
    assert result.periodos_certificados[1].entidad_responsable == "Municipio Dos"


def test_filas_repetidas_entre_tabla_y_texto_se_deduplican():
    header = ["Desde (DD-MM-AAAA)", "Hasta (DD-MM-AAAA)", "Cargo", "Entidad Responsable"]
    tabla = _table(header, ["01-03-1979", "29-12-1984", "Ayudante", "MUNICIPIO DE PRUEBA"])
    pagina_repetida = """
PERIODOS CERTIFICADOS
01-03-1979 29-12-1984 LABORAL PÚBLICO Ayudante ENTIDAD RESPONSABLE: MUNICIPIO DE PRUEBA 0
"""

    result = CetilExtractor().extract_from_pages(
        {1: _PAGE_TEXT, 2: pagina_repetida},
        tables_by_page={1: [tabla]},
    )

    assert len(result.periodos_certificados) == 1


def test_entidad_certificadora_no_incluye_etiquetas():
    texto = """
DATOS DE LA ENTIDAD CERTIFICADORA
Nombre: MUNICIPIO DE CACHIRA Nit: 890,501,776
DATOS DEL EMPLEADO
Tipo de Documento: C
Documento: 1,234,567
FECHA DE NACIMIENTO Enero 1 de 1990
PERIODOS CERTIFICADOS
"""

    result = CetilExtractor().extract_from_pages({1: texto})

    assert result.entidad_certificadora == "MUNICIPIO DE CACHIRA"


def test_tipo_documento_nombre_completo_se_normaliza():
    texto = """
DATOS DEL EMPLEADO
Tipo de Documento: Cédula de Ciudadanía
Documento: 1,234,567
FECHA DE NACIMIENTO Enero 1 de 1990
PERIODOS CERTIFICADOS
"""

    result = CetilExtractor().extract_from_pages({1: texto})

    assert result.trabajador is not None
    assert result.trabajador.tipo_documento == "CC"


def test_pagina_sin_texto_pero_con_tabla_no_bloquea():
    header = ["Desde (DD-MM-AAAA)", "Hasta (DD-MM-AAAA)", "Cargo", "Entidad Responsable"]
    tabla = _table(header, ["01-01-1980", "31-12-1980", "Auxiliar", "MUNICIPIO DE PRUEBA"])

    result = CetilExtractor().extract_from_pages(
        {1: "DOCUMENTO SIN TEXTO ÚTIL"},
        tables_by_page={1: [tabla]},
    )

    assert not any(issue.severity is IssueSeverity.BLOCK for issue in result.issues)
    assert len(result.periodos_certificados) == 1
