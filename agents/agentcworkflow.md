  
  
```mermaid
  flowchart TD
      Start[Alert Fires: CCL 14C 1/19] --> Prog1[Programmatic: Query v_morning_discovery for CCL]
      Prog1 --> Prog2[Programmatic: Query v_symbol_oi_detail for CCL]
      Prog2 --> Prog3[Programmatic: Query flow_alerts history for CCL]

      Prog3 --> Agent1{Agent 1: Flow Classifier}
      Agent1 -->|Input: Alert + OI data| A1Task[Task: Classify flow type<br/>institutional_accumulation?<br/>earnings_play? hedge?]
      A1Task --> A1Out[Output: classification + confidence]

      A1Out --> Agent2{Agent 2: Price Goal Setter}
      Agent2 -->|Input: OI distribution + strikes| A2Task[Task: Identify price target<br/>from OI concentration<br/>and breakeven analysis]
      A2Task --> A2Out[Output: target_price + target_date]

      A2Out --> Agent3{Agent 3: Thesis Builder}
      Agent3 -->|Input: Classification + Goals| A3Task[Task: Determine invalidation<br/>conditions and conviction level]
      A3Task --> A3Out[Output: thesis_status + conditions]

      A3Out --> Prog4[Programmatic: Store fields in tracker]

      Prog4 --> Agent4{Agent 4: Narrative Writer}
      Agent4 -->|Input: All structured data| A4Task[Task: Synthesize natural<br/>language narrative from facts]
      A4Task --> A4Out[Output: narrative text]

      A4Out --> Prog5[Programmatic: Update tracker.narrative]

      Prog5 --> End[Tracker Complete]

      style Agent1 fill:#e1f5ff
      style Agent2 fill:#e1f5ff
      style Agent3 fill:#e1f5ff
      style Agent4 fill:#e1f5ff
      style Prog1 fill:#f0f0f0
      style Prog2 fill:#f0f0f0
      style Prog3 fill:#f0f0f0
      style Prog4 fill:#f0f0f0
      style Prog5 fill:#f0f0f0
'''

