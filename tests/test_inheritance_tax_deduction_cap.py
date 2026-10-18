"""상속세 금융재산상속공제 한도(상속세 및 증여세법 제22조①)."""
import pytest
from korean_tax_calc_mcp.engine.calc_inhgift import _금융재산공제


@pytest.mark.parametrize("net, expected", [
    (15_000_000, 15_000_000),        # 2천만원 이하: 전액
    (50_000_000, 20_000_000),        # 20% 1천만원 < 최소 2천만원
    (500_000_000, 100_000_000),      # 20%
    (1_000_000_000, 200_000_000),    # 20% = 한도
    (1_300_000_000, 200_000_000),    # 20% 2.6억 → 한도 2억
    (5_000_000_000, 200_000_000),
])
def test_financial_asset_deduction_cap(net, expected):
    assert _금융재산공제(2021, net) == expected
