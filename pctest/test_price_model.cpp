#include <pctest/test_price_model.hpp>

namespace pc
{
  void print_usage( std::ostream& out )
  {
    out << "USAGE: test_price_model"
      << "\n  --trade-prices PATH"
      << "\n  --trade-times PATH"
      << "\n  --eval-times PATH"
      << "\n  --eval-prices PATH"
      << "\n  --eval-intervals PATH"
      << "\n  --conf-tolerance FLOAT"
      << "\n  --min-interval FLOAT"
      << "\n  --min-slot-ms INT"
      << "\n  --timeout-ms INT"
      << "\n  --candle-secs INT"
      << "\n  --lookback INT"
      << std::endl;
  }
}

int main( int const argc, char const** const argv )
{
  pc::price_model_test test;
  PC_USAGE( argc % 2 == 1 );
  for ( int i = 1; i + 1 < argc; i += 2 ) {
    std::string const key = argv[ i ];
    std::string const val = argv[ i + 1 ];
    test.set_arg( key, val );
  }
  test.run();
}
