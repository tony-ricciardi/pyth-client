#pragma once

#include <pc/ext/timestamp.hpp>

#include <algorithm>
#include <cstdint>
#include <memory>
#include <optional>

namespace pc
{
  using price_val = int64_t;
  using price_interval = double;

  constexpr auto as_interval( int64_t const x )
  {
    return static_cast< price_interval >( x );
  }

  struct price_time
  {
    price_val price_;
    timestamp time_;
  };

  struct price_estimate
  {
    price_val price_;
    price_interval conf_;
  };

  class price_range
  {
    price_val high_;
    price_val low_;

  public:
    explicit price_range( price_val const open )
      : high_{ open }
      , low_{ open }
    {
    }

    void add_price( price_val const p )
    {
      high_ = std::max( high_, p );
      low_ = std::min( low_, p );
    }

    [[ nodiscard ]]
    price_interval interval() const
    {
      return as_interval( high_ - low_ ) / 2.0;
    }
  };

  template < typename T >
  class trade_tracker
  {
  public:
    using val_t = T;
    using ptr_t = std::shared_ptr< trade_tracker< T > >;

    virtual ~trade_tracker() = default;
    trade_tracker( trade_tracker const& ) = delete;
    trade_tracker& operator=( trade_tracker const& ) = delete;

    virtual void add_trade( price_time ) = 0;
    virtual T eval_at_time( timestamp ) = 0;

  protected:
    trade_tracker() = default;
  };

  using price_model = trade_tracker< std::optional< price_estimate > >;
  using volatility_model = trade_tracker< std::optional< price_interval > >;

  class standard_price_model final
    : public price_model
  {
  public:
    explicit standard_price_model(
      volatility_model::ptr_t = {}
      , std::optional< price_interval > min_conf_interval = {}
      , std::optional< nsecs > timeout_ns = {}
      , std::optional< nsecs > min_slot_ns = {}
      , std::optional< price_interval > init_volatility = {}
    );

    price_model::val_t eval_at_time( timestamp ) override;
    void add_trade( price_time ) override;

  private:
    volatility_model::ptr_t const volatility_model_;

    price_interval const min_interval_;
    price_interval const init_volatility_;
    nsecs const timeout_ns_;
    nsecs const min_slot_ns_;

    std::optional< price_time > last_trade_;
    std::optional< price_range > range_since_eval_;
  };
}
