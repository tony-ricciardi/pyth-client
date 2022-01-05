#pragma once

#include <exception>
#include <sstream>
#include <utility>

namespace pc
{
  class assertion_error
    : public std::exception
  {
    mutable std::string tmp_msg_;

  public:
    std::stringstream msg_;

    char const* what() const noexcept override;

    static assertion_error standard(
      char const* expr
      , char const* file
      , int line
    );

    template < typename T, typename... Args >
    assertion_error&& with_info( T const& arg, Args const&... args )
    {
      msg_ << " (" << arg;
      ( ( msg_ << ", " << args ), ... );
      msg_ << ")";
      return with_info();
    }

    assertion_error&& with_info()
    {
      return std::move( *this );
    }
  };
}

#define PC_LIKELY( expr )   __builtin_expect( expr, true )
#define PC_UNLIKELY( expr ) __builtin_expect( expr, false )

#define PC_VOID static_cast< void >( 0 )

#define PC_GET_ASSERT_ERR( expr ) \
  pc::assertion_error::standard( #expr, __FILE__, __LINE__ )

// Ignores NDEBUG; throws rather than abort (caught by tests, etc.):
#define PC_ASSERT( expr, ... ) ( \
  PC_LIKELY( expr ) \
  ? PC_VOID \
  : throw PC_GET_ASSERT_ERR( expr ).with_info( __VA_ARGS__ ) \
)

#define PC_ASSERT_EQ( a, b ) PC_ASSERT( ( a ) == ( b ), a, b )
#define PC_ASSERT_GE( a, b ) PC_ASSERT( ( a ) >= ( b ), a, b )
#define PC_ASSERT_GT( a, b ) PC_ASSERT( ( a ) > ( b ), a, b )
#define PC_ASSERT_LE( a, b ) PC_ASSERT( ( a ) <= ( b ), a, b )
#define PC_ASSERT_LT( a, b ) PC_ASSERT( ( a ) < ( b ), a, b )
#define PC_ASSERT_PTR( ptr ) PC_ASSERT( ( ptr ) != nullptr )
