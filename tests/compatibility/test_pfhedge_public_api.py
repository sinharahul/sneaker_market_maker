import importlib.metadata

import torch
from pfhedge.nn import EntropicRiskMeasure


def test_pfhedge_023_entropic_risk_measure_public_api() -> None:
    assert importlib.metadata.version("pfhedge") == "0.23.0"
    pnl = torch.tensor([[-1.0, 0.0], [1.0, 2.0]], dtype=torch.float64)
    result = EntropicRiskMeasure(a=0.5)(pnl, target=torch.zeros_like(pnl))
    expected = torch.logsumexp(-0.5 * pnl, dim=0) / 0.5 - torch.log(
        torch.tensor(2.0, dtype=torch.float64)
    ) / 0.5
    assert result.shape == torch.Size([2])
    torch.testing.assert_close(result, expected)
