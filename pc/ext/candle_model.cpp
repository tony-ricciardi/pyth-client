#include <pc/ext/candle_model.hpp>
#include <pc/ext/verify.hpp>

#include <cmath>

namespace pc
{
  static constexpr size_t DEFAULT_LOOKBACK{ 20 };
  static constexpr nsecs DEFAULT_DURATION{ NS_PER_MIN * 1 };

  candle_model::candle_model(
    std::optional< size_t > const lookback
    , std::optional< nsecs > const candle_ns
  )
    : capacity_{ 1 + lookback.value_or( DEFAULT_LOOKBACK ) }
    , candle_ns_{ candle_ns.value_or( DEFAULT_DURATION ) }
    , count_{ 0 }
    , front_{ 0 }
  {
    PC_ASSERT_GT( capacity_, 1 );  // current + lookback
    PC_ASSERT_GT( candle_ns_, 0 );

    highs_.resize( capacity_ );
    lows_.resize( capacity_ );
    starts_.resize( capacity_ );
  }

  void candle_model::add_trade( price_time const trade )
  {
    auto const price = as_interval( trade.price_ );
    auto const start = floor_time( trade.time_, candle_ns_ );

    if ( count_ == 0 || start > starts_[ front_ ] ) {
      // Prepend new candle.
      front_ = ( front_ + capacity_ - 1 ) % capacity_;
      count_ = std::min( count_ + 1, capacity_ );
      highs_[ front_ ] = price;
      lows_[ front_ ] = price;
      starts_[ front_ ] = start;
    }

    PC_ASSERT_EQ( start, starts_[ front_ ] );
    highs_[ front_ ] = std::max( highs_[ front_ ], price );
    lows_[ front_ ] = std::min( lows_[ front_ ], price );
  }

  std::optional< price_interval >
  candle_model::eval_volatility() const
  {
    PC_ASSERT_LE( count_, capacity_ );
    if ( count_ < capacity_ ) {
      return {};
    }

    price_interval numer = 0;
    price_interval denom = 0;

    for ( size_t i = 0; i + 1 < count_; ++i ) {
      auto const cur = ( front_ + i ) % capacity_;
      auto const prev = ( cur + 1 ) % capacity_;

      auto const max_high = std::max( highs_[ cur ], highs_[ prev ] );
      auto const min_low = std::min( lows_[ cur ], lows_[ prev ] );
      auto const log_ratio = std::log( max_high / min_low );
      PC_ASSERT_GT( min_low, 0 );
      PC_ASSERT_LE( min_low, max_high );
      numer += log_ratio * log_ratio;

      auto const prev_start = starts_[ prev ];
      auto const cur_end = add_time( starts_[ cur ], candle_ns_ );
      PC_ASSERT_GT( cur_end, prev_start );
      denom += as_interval( diff_times( cur_end, prev_start ) );
    }

    denom *= std::log( 2 ) * 4.0;
    auto constexpr ns_per_year = as_interval( NS_PER_YEAR );  // annualized
    return { std::sqrt( numer / denom * ns_per_year ) };
  }
}
