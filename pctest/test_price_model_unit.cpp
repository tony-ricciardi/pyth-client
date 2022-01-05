#include <pctest/test_price_model.hpp>

using namespace pc;

namespace pc
{
  void print_usage( std::ostream& ) {}
}

struct stub_volatility_model
  : public volatility_model
{
  std::optional< price_interval > vol_;

  explicit stub_volatility_model( std::optional< price_interval > const vol )
    : vol_{ vol }
  {
  }

  std::optional< price_interval > eval_at_time( timestamp ) override
  {
    return vol_;
  }

  void add_trade( price_time ) override {}
};

struct eval_info
{
  timestamp time_;
  price_val price_;
  price_interval conf_;
};

struct unit_test
  : public price_model_test
{
  volatility_model::ptr_t vol_model_;
  std::vector< price_time > trades_;
  std::vector< eval_info > evals_;

  volatility_model::ptr_t make_vol_model() override
  {
    return vol_model_ ?: price_model_test::make_vol_model();
  }

  void set_stub_vol( std::optional< price_interval > const vol )
  {
    vol_model_ = std::make_shared< stub_volatility_model >( vol );
  }

  template < typename T >
  static auto make_col( std::vector< T > const& impl )
  {
    auto col = std::make_shared< vec_column< T > >();
    col->impl_.assign( impl.begin(), impl.end() );
    return col;
  }

  void run() override
  {
    {
      std::vector< timestamp > trade_times;
      std::vector< price_val > trade_prices;
      for ( auto const& t : trades_ ) {
        trade_times.push_back( t.time_ );
        trade_prices.push_back( t.price_ );
      }
      trade_times_ = make_col( trade_times );
      trade_prices_ = make_col( trade_prices );
    }

    {
      std::vector< timestamp > eval_times;
      std::vector< price_val > eval_prices;
      std::vector< price_interval > eval_confs;
      for ( auto const& e : evals_ ) {
        eval_times.push_back( e.time_ );
        eval_prices.push_back( e.price_ );
        eval_confs.push_back( e.conf_ );
      }
      eval_times_ = make_col( eval_times );
      eval_prices_ = make_col( eval_prices );
      eval_intervals_ = make_col( eval_confs );
    }

    price_model_test::run();
  }
};

static void test_empty()
{
  unit_test test;
  test.set_stub_vol( {} );
  test.run();
}

int main( int const argc, char const** )
{
  PC_USAGE( argc == 1 );
  test_empty();
}
