#pragma once

#include <pc/ext/price_model.hpp>

#include <optional>
#include <vector>

namespace pc
{
  class candle_model final
    : public volatility_model
  {
  public:
    explicit candle_model(
      std::optional< size_t > lookback = {}
      , std::optional< nsecs > candle_ns = {}
    );

    [[ nodiscard, gnu::flatten ]]
    volatility_model::val_t eval_volatility() const;
    volatility_model::val_t eval_at_time( timestamp ) override
    {
      return eval_volatility();
    }

    void add_trade( price_time ) override;

  private:
    size_t const capacity_;
    nsecs const candle_ns_;

    size_t count_;
    size_t front_;

    // TODO aligned allocator or eigen::Matrix
    std::vector< timestamp > starts_;
    std::vector< price_interval > highs_;
    std::vector< price_interval > lows_;
  };
}
