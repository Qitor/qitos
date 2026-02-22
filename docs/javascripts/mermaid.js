document$.subscribe(() => {
  if (typeof mermaid === 'undefined') return;
  mermaid.initialize({
    startOnLoad: true,
    securityLevel: 'loose',
    theme: 'base',
    themeVariables: {
      background: '#ffffff',
      primaryColor: '#f7fafc',
      primaryTextColor: '#102a43',
      primaryBorderColor: '#c8d7e1',
      lineColor: '#6b7f92',
      tertiaryColor: '#ffffff',
      fontFamily: 'Manrope, Noto Serif SC, serif'
    },
    flowchart: {
      curve: 'linear',
      htmlLabels: true
    }
  });
  mermaid.run({ querySelector: '.mermaid' });
});
