#pragma once

#include <pctest/column.hpp>
#include <pctest/usage.hpp>

#include <pc/ext/candle_model.hpp>
#include <pc/ext/price_model.hpp>

#include <limits>
#include <optional>
#include <memory>

namespace pc
{
  struct price_model_test
  {
    virtual ~price_model_test() = default;

    template < typename T >
    using col_ptr = std::shared_ptr< pc::column< T > >;

    // Input and expected output data
    col_ptr< pc::timestamp > trade_times_;
    col_ptr< pc::price_val > trade_prices_;
    col_ptr< pc::timestamp > eval_times_;
    col_ptr< pc::price_val > eval_prices_;
    col_ptr< pc::price_interval > eval_intervals_;

    // Model args
    std::optional< pc::price_interval > min_interval_;
    std::optional< pc::price_interval > init_volatility_;
    std::optional< pc::nsecs > timeout_ns_;
    std::optional< pc::nsecs > min_slot_ns_;
    std::optional< pc::nsecs > candle_ns_;
    std::optional< size_t > lookback_candles_;

    // Test args
    std::optional< pc::price_interval > conf_tolerance_;

    virtual price_model::ptr_t make_price_model()
    {
      return std::make_shared< standard_price_model >(
        make_vol_model()
        , min_interval_
        , timeout_ns_
        , min_slot_ns_
        , init_volatility_
      );
    }

    virtual volatility_model::ptr_t make_vol_model()
    {
      return std::make_shared< pc::candle_model >(
        lookback_candles_
        , candle_ns_
      );
    }

    template < typename T, typename... Args >
    static T& init_opt( std::optional< T >& opt, Args const&... args )
    {
      PC_USAGE( ! opt.has_value() );
      return opt.emplace( args... );
    }

    template < typename Impl, typename Base, typename... Args >
    static Impl& init_ptr( std::shared_ptr< Base >& ptr, Args const&... args )
    {
      PC_USAGE( ! ptr );
      auto impl = std::make_shared< Impl >( args... );
      ptr = impl;
      return *impl;
    }

    template < typename T >
    static auto& init_file( col_ptr< T >& ptr, std::string const& path )
    {
      return init_ptr< file_column< T > >( ptr, path );
    }

    template < typename T >
    static T& parse_opt( std::string const& arg, std::optional< T >& opt )
    {
      auto& val = init_opt( opt );
      std::stringstream ss{ arg };
      char ch;
      PC_USAGE( ! arg.empty() );
      PC_USAGE( ss >> val && ! ss.get( ch ), val );
      return val;
    }

    virtual void set_arg( std::string const& key, std::string const& val )
    {
      if ( key == "--trade-prices" ) {
        init_file( trade_prices_, val );
      }
      else if ( key == "--trade-times" ) {
        init_file( trade_times_, val );
      }
      else if ( key == "--eval-times" ) {
        init_file( eval_times_, val );
      }
      else if ( key == "--eval-prices" ) {
        init_file( eval_prices_, val );
      }
      else if ( key == "--eval-intervals" ) {
        init_file( eval_intervals_, val );
      }
      else if ( key == "--init-volatility" ) {
        parse_opt( val, init_volatility_ );
      }
      else if ( key == "--min-interval" ) {
        parse_opt( val, min_interval_ );
      }
      else if ( key == "--min-slot-ms" ) {
        parse_opt( val, min_slot_ns_ ) *= pc::NS_PER_MS;
      }
      else if ( key == "--timeout-ms" ) {
        parse_opt( val, timeout_ns_ ) *= pc::NS_PER_MS;
      }
      else if ( key == "--candle-secs" ) {
        parse_opt( val, candle_ns_ ) *= pc::NS_PER_SEC;
      }
      else if ( key == "--lookback" ) {
        parse_opt( val, lookback_candles_ );
      }
      else if ( key == "--conf-tolerance" ) {
        parse_opt( val, conf_tolerance_ );
      }
      else {
        PC_USAGE( false, key );
      }
    }

    virtual void validate_args()
    {
      PC_USAGE( trade_times_ && trade_prices_ );
      PC_USAGE( eval_times_ && eval_prices_ && eval_intervals_ );

      PC_USAGE( trade_times_->size() == trade_prices_->size() );
      PC_USAGE( eval_times_->size() == eval_prices_->size() );
      PC_USAGE( eval_times_->size() == eval_intervals_->size() );

      PC_USAGE( init_volatility_.value_or( 0 ) >= 0 );
      PC_USAGE( min_interval_.value_or( 0 ) >= 0 );
      PC_USAGE( min_slot_ns_.value_or( 0 ) >= 0 );
      PC_USAGE( timeout_ns_.value_or( 1 ) > 0 );
      PC_USAGE( candle_ns_.value_or( 1 ) > 0 );
      PC_USAGE( lookback_candles_.value_or( 1 ) > 0 );
      PC_USAGE( conf_tolerance_.value_or( 0 ) >= 0 );
    }

    virtual void run()
    {
      validate_args();

      size_t const trade_count = trade_prices_->size();
      auto* const trade_prices = trade_prices_->begin();
      auto* const trade_times = trade_times_->begin();
      for ( size_t i = 1; i < trade_count; ++i) {
        PC_ASSERT_LE( trade_times[ i - 1 ], trade_times[ i ] );
      }

      size_t const eval_count = eval_prices_->size();
      auto* const eval_prices = eval_prices_->begin();
      auto* const eval_times = eval_times_->begin();
      auto* const eval_confs = eval_intervals_->begin();
      for ( size_t i = 1; i < eval_count; ++i) {
        PC_ASSERT_LE( eval_times[ i - 1 ], eval_times[ i ] );
        PC_ASSERT_GE( eval_confs[ i ], 0 );
      }

      // Same default rtol as np.allclose:
      auto const conf_tol = conf_tolerance_.value_or( 0.00001 );

      auto model = make_price_model();
      size_t eval_idx = 0;
      size_t trade_idx = 0;

      while ( true ) {
        auto const eval_time = (
          eval_idx < eval_count
          ? eval_times[ eval_idx ]
          : std::numeric_limits< timestamp >::max()
        );

        if ( trade_idx < trade_count && eval_time > trade_times[ trade_idx ] ) {
          model->add_trade( {
            .price_ = trade_prices[ trade_idx ]
            , .time_ = trade_times[ trade_idx ]
          } );
          ++trade_idx;
        }

        else if ( eval_idx < eval_count ) {
          auto const expected_price = eval_prices[ eval_idx ];
          auto const expected_conf = eval_confs[ eval_idx ];
          auto const actual = model->eval_at_time( eval_time );

          if ( actual.has_value() ) {
            PC_ASSERT_EQ( actual->price_, expected_price );
            PC_ASSERT_GE( actual->conf_, expected_conf * ( 1 - conf_tol ));
            PC_ASSERT_LE( actual->conf_, expected_conf * ( 1 + conf_tol ));
          }
          else {
            PC_ASSERT_EQ( expected_price, 0 );
            PC_ASSERT_EQ( expected_conf, 0 );
          }

          ++eval_idx;
        }

        else {
          break;
        }
      }

      PC_ASSERT_EQ( trade_idx, trade_count );
      PC_ASSERT_EQ( eval_idx, eval_count );
    }
  };
}
