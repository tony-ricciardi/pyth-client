#include <pc/ext/price_model.hpp>

#include <pc/ext/candle_model.hpp>
#include <pc/ext/verify.hpp>

#include <cmath>

namespace pc
{
  static constexpr nsecs DEFAULT_TIMEOUT{ NS_PER_SEC * 60 };
  static constexpr nsecs DEFAULT_MIN_SLOT{ NS_PER_MS * 500 };
  static constexpr price_interval DEFAULT_MIN_INTERVAL{ 0.01 };
  static constexpr price_interval DEFAULT_VOLATILITY{ 1.0 };

  standard_price_model::standard_price_model(
    volatility_model::ptr_t vol_model
    , std::optional< price_interval > const min_conf_interval
    , std::optional< nsecs > const timeout
    , std::optional< nsecs > const min_slot_ns
    , std::optional< price_interval > const init_volatility
  )
    : volatility_model_{
        vol_model
        ? std::move( vol_model )
        : std::make_shared< candle_model >()
      }
    , min_interval_{ min_conf_interval.value_or( DEFAULT_MIN_INTERVAL ) }
    , init_volatility_{ init_volatility.value_or( DEFAULT_VOLATILITY ) }
    , timeout_ns_{ timeout.value_or( DEFAULT_TIMEOUT ) }
    , min_slot_ns_{ min_slot_ns.value_or( DEFAULT_MIN_SLOT ) }
  {
    PC_ASSERT_PTR( volatility_model_.get() );
    PC_ASSERT_GE( min_interval_, 0 );
    PC_ASSERT_GE( init_volatility_, 0 );
    PC_ASSERT_GE( min_slot_ns_, 0 );
    PC_ASSERT_LT( min_slot_ns_, timeout_ns_ );
  }

  void standard_price_model::add_trade( price_time const trade )
  {
    auto const price = trade.price_;
    volatility_model_->add_trade( trade );
    if ( PC_UNLIKELY( ! range_since_eval_.has_value() ) ) {
      range_since_eval_.emplace( price );
    }
    range_since_eval_->add_price( price );
    last_trade_.emplace( trade );
  }

  std::optional< price_estimate >
  standard_price_model::eval_at_time( timestamp const now )
  {
    if ( PC_UNLIKELY( ! last_trade_.has_value() ) ) {
      return {};
    }

    auto const ns_since_trade = diff_times( now, last_trade_->time_ );
    PC_ASSERT_GE( ns_since_trade, 0 );
    if ( PC_UNLIKELY( ns_since_trade > timeout_ns_ ) ) {
      return {};
    }

    auto const yearly_vol = volatility_model_->eval_at_time( now );
    auto const years_since_trade = (
      as_interval( std::max( ns_since_trade, min_slot_ns_ ) )
      / as_interval( NS_PER_YEAR )
    );

    price_interval conf_interval{
      yearly_vol.value_or( init_volatility_ )
      * std::sqrt( years_since_trade )
      * as_interval( last_trade_->price_ )
    };

    conf_interval = std::max( conf_interval, min_interval_ );
    if ( PC_LIKELY( range_since_eval_.has_value() ) ) {
      conf_interval = std::max( conf_interval, range_since_eval_->interval() );
      range_since_eval_.reset();
    }

    return { { last_trade_->price_, conf_interval } };
  }
}
