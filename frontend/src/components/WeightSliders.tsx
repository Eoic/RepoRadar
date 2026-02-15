interface WeightSlidersProps {
  purposeWeight: number;
  onWeightChange: (purpose: number) => void;
}

export function WeightSliders({ purposeWeight, onWeightChange }: WeightSlidersProps) {
  const stackWeight = Math.round((1 - purposeWeight) * 100) / 100;
  const purposePct = Math.round(purposeWeight * 100);
  const stackPct = Math.round(stackWeight * 100);

  return (
    <div className="weight-sliders">
      <div className="weight-header">
        <span className="weight-label" id="weight-controls-label">Signal Weights</span>
      </div>
      <div className="weight-row">
        <div className="weight-info">
          <span className="weight-name">Purpose</span>
          <span className="weight-value" aria-label={`Purpose weight: ${purposePct}%`}>{purposePct}%</span>
        </div>
        <input
          type="range"
          min="0"
          max="100"
          value={purposePct}
          onChange={(e) => onWeightChange(Number(e.target.value) / 100)}
          className="weight-slider"
          aria-labelledby="weight-controls-label"
          aria-label="Adjust purpose vs stack weight"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={purposePct}
          aria-valuetext={`Purpose ${purposePct}%, Stack ${stackPct}%`}
        />
        <div className="weight-info">
          <span className="weight-name">Stack</span>
          <span className="weight-value" aria-label={`Stack weight: ${stackPct}%`}>{stackPct}%</span>
        </div>
      </div>
    </div>
  );
}
