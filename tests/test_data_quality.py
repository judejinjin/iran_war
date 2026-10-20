from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from analysis.data_quality import run_quality_pass
from db.database import Base, FuturesCurve, OptionsChain


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_run_quality_pass_repairs_futures_and_options():
    session = build_session()

    session.add(FuturesCurve(
        date=date(2026, 9, 10),
        symbol="CL",
        contract_month="2026-09",
        settlement_price=None,
        volume=42,
    ))
    session.add(FuturesCurve(
        date=date(2026, 9, 10),
        symbol="CL",
        contract_month="2026-10",
        settlement_price=74.0,
        volume=50,
    ))

    session.add(OptionsChain(
        date=date(2026, 9, 10),
        underlying="CL",
        expiry_date=date(2026, 10, 15),
        strike=75.0,
        option_type="CALL",
        bid=1.0,
        ask=1.5,
        last_price=None,
        volume=None,
    ))

    session.commit()

    report = run_quality_pass(session, fix=True)

    assert report["futures"]["status"] in {"healthy", "fixed"}
    assert report["options"]["status"] in {"healthy", "fixed"}
    futures_rows = session.query(FuturesCurve).filter_by(symbol="CL", date=date(2026, 9, 10)).count()
    assert futures_rows == 1

    option_rows = session.query(OptionsChain).filter_by(
        date=date(2026, 9, 10),
        underlying="CL",
        expiry_date=date(2026, 10, 15),
        strike=75.0,
    ).all()
    assert len(option_rows) >= 2
    assert any(row.option_type == "PUT" for row in option_rows)
    assert any(row.last_price is not None for row in option_rows)

    session.close()
