(async () => {
  const symbols = ['HPE','MTN','ORCL','CPB','ADBE','DG','JBL','DLTR','DOCU','GIS','FIVE','LEN','MU','NKE','UEC','ACN','CCL','DRI','FDS','FDX','MKC','CNM','CNXC','CTAS','GME','JEF','PAYX','PII','LULU','PVH','AES','CAG','LW','XOM'];
  const results = [];

  for (const sym of symbols) {
    try {
      const instResp = await fetch("https://api.robinhood.com/instruments/?active_instruments_only=false&symbol=" + sym);
      const instData = await instResp.json();
      if (!instData.results || !instData.results.length) { results.push({symbol: sym, error: "no instrument"}); continue; }
      const instUrl = instData.results[0].url;

      const earnResp = await fetch("https://api.robinhood.com/marketdata/earnings/?instrument=" + encodeURIComponent(instUrl));
      const earnData = await earnResp.json();

      const today = new Date().toISOString().split("T")[0];
      const upcoming = earnData.results
        .filter(function(e) { return e.report && e.report.date >= today; })
        .sort(function(a, b) { return a.report.date.localeCompare(b.report.date); });

      if (upcoming.length > 0) {
        var e = upcoming[0];
        results.push({
          symbol: sym,
          date: e.report.date,
          timing: e.report.timing,
          verified: e.report.verified,
          quarter: e.quarter,
          year: e.year
        });
      } else {
        results.push({symbol: sym, error: "no upcoming earnings"});
      }

      await new Promise(function(r) { setTimeout(r, 300); });
    } catch (err) {
      results.push({symbol: sym, error: err.message});
    }
  }

  var output = JSON.stringify(results, null, 2);
  console.log(output);
  copy(output);
  console.log("--- COPIED TO CLIPBOARD ---");
})();
