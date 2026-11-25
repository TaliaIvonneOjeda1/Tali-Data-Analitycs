from datetime import date

from src.reporting.names import informe_pdf_filename, informe_stem


def test_consultas_desde_sesion():
    assert (
        informe_stem("sesion_abc", from_session=True, when=date(2026, 11, 25))
        == "Informe20261125-Consultas"
    )
    assert (
        informe_pdf_filename(None, from_session=True, when=date(2026, 11, 25))
        == "Informe20261125-Consultas.pdf"
    )


def test_consultas_adhoc():
    assert (
        informe_stem("adhoc", when=date(2026, 11, 25)) == "Informe20261125-Consultas"
    )


def test_ejecutivo_predefinidos():
    for iid in ("I1", "I2", "I3"):
        assert (
            informe_stem(iid, when=date(2026, 11, 25)) == "Informe20261125-ejecutivo"
        )
        assert (
            informe_pdf_filename(iid, when=date(2026, 11, 25))
            == "Informe20261125-ejecutivo.pdf"
        )


def test_sesion_sin_flag_por_prefijo():
    assert (
        informe_stem("sesion_3f56925bef", when=date(2026, 11, 25))
        == "Informe20261125-Consultas"
    )
