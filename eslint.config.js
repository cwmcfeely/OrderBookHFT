export default [
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        window: "readonly",
        document: "readonly",
        fetch: "readonly",
        alert: "readonly",
        setInterval: "readonly",
        Plotly: "readonly", // if Plotly is loaded via <script>
        // Add any additional globals you use:
        symbols: "readonly",
        bid: "readonly",
        ask: "readonly",
        rows: "readonly",
        openTab: "readonly",
        toggleExchange: "readonly",
        toggleMyStrategy: "readonly",
        cancelMyStrategyOrders: "readonly",
        inventoryPercentClass: "readonly",
        hideStatusError: "readonly",
        data: "readonly",
        err: "readonly"
      }
    },
    rules: {
      "no-unused-vars": "warn",
      "no-undef": "error",
      "no-console": "off",
      "eqeqeq": "error",
      "curly": "error"
    }
  }
];