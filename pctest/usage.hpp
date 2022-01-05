#pragma once

#include <pc/ext/verify.hpp>

#include <iostream>
#include <utility>

namespace pc
{
  void print_usage( std::ostream& );

  inline void throw_usage( pc::assertion_error&& err )
  {
    err.msg_ << std::endl;
    print_usage( err.msg_ );
    throw std::move( err );
  }
}

#define PC_USAGE( expr, ... ) ( \
  PC_LIKELY( expr ) ? PC_VOID : pc::throw_usage( \
    PC_GET_ASSERT_ERR( expr ).with_info( __VA_ARGS__ ) \
  ) \
)
